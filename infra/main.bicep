// infra/main.bicep
// Production-grade deployment for Azure RAG agent runtime and dependencies

@description('Azure region')
param location string = 'eastus'

@description('Project short name')
param projectName string = 'ragagent'

@description('Environment name')
param environment string = 'prod'

@description('Deploy Redis Enterprise (Stack modules) instead of Premium Redis')
param useRedisEnterprise bool = true

@description('Enable Synapse serverless only (recommended). If you set false, this template will still create PEs for dedicated SQL if you add it later.')
param synapseServerlessOnly bool = true

var namePrefix = '${projectName}-${environment}'

var tags = {
  project: projectName
  env: environment
}

// -------------------------
// Networking
// -------------------------
resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name: '${projectName}-vnet-${environment}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.0.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'container-apps-subnet'
        properties: {
          addressPrefix: '10.0.0.0/23'
          delegations: [
            {
              name: 'Microsoft.App/environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'private-endpoints-subnet'
        properties: {
          addressPrefix: '10.0.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'apim-subnet'
        properties: {
          addressPrefix: '10.0.3.0/24'
        }
      }
    ]
  }
}

// -------------------------
// Log Analytics + App Insights
// -------------------------
resource logws 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${projectName}-logs-${environment}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appins 'Microsoft.Insights/components@2020-02-02' = {
  name: '${projectName}-insights-${environment}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logws.id
  }
}

// -------------------------
// Front Door (Premium) with APIM as Private Link Origin
// -------------------------
resource afdProfile 'Microsoft.Cdn/profiles@2023-05-01' = {
  name: '${projectName}-fd-${environment}'
  location: 'global'
  sku: {
    name: 'Premium_AzureFrontDoor'
  }
  tags: tags
  properties: {
    originResponseTimeoutSeconds: 60
  }
}

resource afdEndpoint 'Microsoft.Cdn/profiles/afdEndpoints@2023-05-01' = {
  name: '${projectName}-${environment}'
  parent: afdProfile
  location: 'global'
  properties: {
    enabledState: 'Enabled'
  }
}

// -------------------------
// API Management (Premium) - Internal VNet
// -------------------------
resource apim 'Microsoft.ApiManagement/service@2023-05-01' = {
  name: '${projectName}-apim-${environment}'
  location: location
  tags: tags
  sku: {
    name: 'Premium'
    capacity: 1
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: 'admin@example.com'
    publisherName: 'RAG Agent'
    virtualNetworkType: 'Internal'
    virtualNetworkConfiguration: {
      subnetResourceId: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'apim-subnet')
    }
  }
}

resource apimProdFree 'Microsoft.ApiManagement/service/products@2023-05-01' = {
  name: 'free'
  parent: apim
  properties: {
    displayName: 'Free'
    description: '100 req/hour'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
  }
}

resource apimProdPro 'Microsoft.ApiManagement/service/products@2023-05-01' = {
  name: 'pro'
  parent: apim
  properties: {
    displayName: 'Pro'
    description: '10k req/day'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
  }
}

resource apimPolicy 'Microsoft.ApiManagement/service/policies@2023-05-01' = {
  name: 'policy'
  parent: apim
  properties: {
    format: 'xml'
    value: '''
    <policies>
      <inbound>
        <base />
        <validate-jwt header-name="Authorization" failed-validation-httpcode="401">
          <openid-config url="https://login.microsoftonline.com/@(context.Variables.GetValueOrDefault("tenant","common"))/.well-known/openid-configuration" />
          <audiences>
            <audience>api://${projectName}</audience>
          </audiences>
        </validate-jwt>
        <set-header name="x-tenant-id" exists-action="override">
          <value>@(context.Request.Headers.GetValueOrDefault("Authorization","").AsJwt()?.Claims.GetValueOrDefault("tid",""))</value>
        </set-header>
        <choose>
          <when condition="@(context.Product?.Name == "Free")">
            <quota-by-key calls="100" renewal-period="3600" counter-key="@(context.Subscription?.Key)" />
            <rate-limit-by-key calls="10" renewal-period="60" counter-key="@(context.Subscription?.Key)" />
          </when>
          <otherwise>
            <quota-by-key calls="10000" renewal-period="86400" counter-key="@(context.Subscription?.Key)" />
            <rate-limit-by-key calls="100" renewal-period="60" counter-key="@(context.Subscription?.Key)" />
          </otherwise>
        </choose>
        <validate-content unspecified-content-type-action="prevent" max-size="10240" size-exceeded-action="prevent" />
        <cors>
          <allowed-origins>
            <origin>*</origin>
          </allowed-origins>
        </cors>
      </inbound>
      <backend>
        <forward-request timeout="60" />
      </backend>
      <outbound>
        <set-header name="X-Response-Time" exists-action="override">
          <value>@(context.Elapsed.TotalMilliseconds.ToString())</value>
        </set-header>
      </outbound>
      <on-error>
        <return-response>
          <set-status code="500" />
        </return-response>
      </on-error>
    </policies>
    '''
  }
}

// -------------------------
// Container Apps Env (VNet) + Container App (internal ingress)
// -------------------------
resource cae 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${projectName}-env-${environment}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logws.properties.customerId
        sharedKey: logws.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'container-apps-subnet')
    }
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-06-01-preview' = {
  name: '${projectName}acr${environment}'
  location: location
  sku: {
    name: 'Premium'
  }
  tags: tags
  properties: {
    adminUserEnabled: false
  }
}

resource ca 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${projectName}-api-${environment}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      ingress: {
        external: false
        targetPort: 8080
        transport: 'http'
      }
      registries: [
        {
          server: '${acr.name}.azurecr.io'
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'appins-conn'
          value: appins.properties.ConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'rag-agent-api'
          image: '${acr.name}.azurecr.io/rag-agent:latest'
          resources: {
            cpu: 2.0
            memory: '4Gi'
          }
          env: [
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appins-conn'
            }
            {
              name: 'PROJECT_ENV'
              value: environment
            }
          ]
        }
      ]
      scale: {
        minReplicas: 2
        maxReplicas: 10
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ca.id, acr.id, 'acrpull')
  scope: acr
  properties: {
    principalId: ca.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalType: 'ServicePrincipal'
  }
}

// -------------------------
// Key Vault
// -------------------------
resource kv 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: '${projectName}-kv-${environment}'
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    }
  }
}

resource kvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ca.id, kv.id, 'kv-secrets-user')
  scope: kv
  properties: {
    principalId: ca.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalType: 'ServicePrincipal'
  }
}

// -------------------------
// Azure OpenAI (Private Link) + deployments
// -------------------------
resource aoai 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: '${projectName}-openai-${environment}'
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    customSubDomainName: '${projectName}-openai-${environment}'
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
    }
  }
}

resource depGpt4o 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  name: 'gpt-4o'
  parent: aoai
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-08-06'
    }
  }
}

resource depMini 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  name: 'gpt-4o-mini'
  parent: aoai
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
  }
  dependsOn: [
    depGpt4o
  ]
}

resource depEmb 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  name: 'text-embedding-3-small'
  parent: aoai
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
      version: '1'
    }
  }
  dependsOn: [
    depMini
  ]
}

resource peAoai 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-openai-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'aoai'
        properties: {
          privateLinkServiceId: aoai.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource pdzAoai 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.openai.azure.com'
  location: 'global'
}

resource pdzAoaiLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: '${namePrefix}-aoai-link'
  parent: pdzAoai
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource pdzgAoai 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'default'
  parent: peAoai
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'aoai'
        properties: {
          privateDnsZoneId: pdzAoai.id
        }
      }
    ]
  }
}

// -------------------------
// Azure AI Search (Private Link)
// -------------------------
resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: '${projectName}-search-${environment}'
  location: location
  sku: {
    name: 'standard'
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    replicaCount: 2
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'Disabled'
    networkRuleSet: {
      ipRules: []
    }
  }
}

resource peSearch 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-search-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'search'
        properties: {
          privateLinkServiceId: search.id
          groupIds: [
            'searchService'
          ]
        }
      }
    ]
  }
}

resource pdzSearch 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.search.windows.net'
  location: 'global'
}

resource pdzSearchLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: '${namePrefix}-search-link'
  parent: pdzSearch
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource pdzgSearch 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'default'
  parent: peSearch
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'search'
        properties: {
          privateDnsZoneId: pdzSearch.id
        }
      }
    ]
  }
}

// -------------------------
// Cosmos DB (SQL + Gremlin) Private Link
// -------------------------
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2023-11-15' = {
  name: '${projectName}-cosmos-${environment}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
    capabilities: [
      {
        name: 'EnableGremlin'
      }
    ]
    publicNetworkAccess: 'Disabled'
    networkAclBypass: 'None'
  }
}

resource cosmosSqlDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-11-15' = {
  name: 'rag_agent'
  parent: cosmos
  properties: {
    resource: {
      id: 'rag_agent'
    }
  }
}

resource cosmosGremlinDb 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2023-11-15' = {
  name: 'graph'
  parent: cosmos
  properties: {
    resource: {
      id: 'graph'
    }
  }
}

resource peCosmos 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-cosmos-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'cosmos-sql'
        properties: {
          privateLinkServiceId: cosmos.id
          groupIds: [
            'Sql'
          ]
        }
      }
      {
        name: 'cosmos-gremlin'
        properties: {
          privateLinkServiceId: cosmos.id
          groupIds: [
            'Gremlin'
          ]
        }
      }
    ]
  }
}

resource pdzCosmosSql 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.documents.azure.com'
  location: 'global'
}

resource pdzCosmosGremlin 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.gremlin.cosmos.azure.com'
  location: 'global'
}

resource pdzCosmosSqlLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: '${namePrefix}-cosmos-sql-link'
  parent: pdzCosmosSql
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource pdzCosmosGremlinLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: '${namePrefix}-cosmos-gremlin-link'
  parent: pdzCosmosGremlin
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource pdzgCosmos 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'default'
  parent: peCosmos
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'sql'
        properties: {
          privateDnsZoneId: pdzCosmosSql.id
        }
      }
      {
        name: 'gremlin'
        properties: {
          privateDnsZoneId: pdzCosmosGremlin.id
        }
      }
    ]
  }
}

// -------------------------
// Redis: Enterprise (Stack) or Premium
// -------------------------
resource redisEnt 'Microsoft.Cache/redisEnterprise@2023-07-01' = if (useRedisEnterprise) {
  name: '${projectName}-redis-${environment}'
  location: location
  tags: tags
  sku: {
    name: 'Enterprise_E10-2'
  }
  properties: {
    minimumTlsVersion: '1.2'
  }
}

resource redisEntDb 'Microsoft.Cache/redisEnterprise/databases@2023-07-01' = if (useRedisEnterprise) {
  name: 'default'
  parent: redisEnt
  properties: {
    clientProtocol: 'Encrypted'
    port: 10000
    modules: [
      {
        name: 'RedisJSON'
      }
      {
        name: 'RediSearch'
      }
    ]
  }
}

resource peRedisEnt 'Microsoft.Network/privateEndpoints@2023-05-01' = if (useRedisEnterprise) {
  name: '${namePrefix}-redis-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'redis'
        properties: {
          privateLinkServiceId: redisEnt.id
          groupIds: [
            'redisEnterprise'
          ]
        }
      }
    ]
  }
}

resource pdzRedisEnt 'Microsoft.Network/privateDnsZones@2020-06-01' = if (useRedisEnterprise) {
  name: 'privatelink.redisenterprise.cache.azure.net'
  location: 'global'
}

resource pdzRedisEntLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (useRedisEnterprise) {
  name: '${namePrefix}-redis-link'
  parent: pdzRedisEnt
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource pdzgRedisEnt 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = if (useRedisEnterprise) {
  name: 'default'
  parent: peRedisEnt
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'redis'
        properties: {
          privateDnsZoneId: pdzRedisEnt.id
        }
      }
    ]
  }
}

resource redisStd 'Microsoft.Cache/redis@2023-08-01' = if (!useRedisEnterprise) {
  name: '${projectName}-redis-${environment}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'Premium'
      family: 'P'
      capacity: 1
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    redisConfiguration: {
      'maxmemory-policy': 'allkeys-lru'
    }
  }
}

resource peRedisStd 'Microsoft.Network/privateEndpoints@2023-05-01' = if (!useRedisEnterprise) {
  name: '${namePrefix}-redis-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'redis'
        properties: {
          privateLinkServiceId: redisStd.id
          groupIds: [
            'redisCache'
          ]
        }
      }
    ]
  }
}

resource pdzRedisStd 'Microsoft.Network/privateDnsZones@2020-06-01' = if (!useRedisEnterprise) {
  name: 'privatelink.redis.cache.windows.net'
  location: 'global'
}

resource pdzRedisStdLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (!useRedisEnterprise) {
  name: '${namePrefix}-redis-link'
  parent: pdzRedisStd
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource pdzgRedisStd 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = if (!useRedisEnterprise) {
  name: 'default'
  parent: peRedisStd
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'redis'
        properties: {
          privateDnsZoneId: pdzRedisStd.id
        }
      }
    ]
  }
}

// -------------------------
// Storage (ADLS Gen2) + Private Endpoints (blob, dfs)
// -------------------------
resource sa 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: '${projectName}storage${environment}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Disabled'
  }
}

resource peBlob 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-blob-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'blob'
        properties: {
          privateLinkServiceId: sa.id
          groupIds: [
            'blob'
          ]
        }
      }
    ]
  }
}

resource peDfs 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-dfs-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'dfs'
        properties: {
          privateLinkServiceId: sa.id
          groupIds: [
            'dfs'
          ]
        }
      }
    ]
  }
}

resource pdzBlob 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.blob.core.windows.net'
  location: 'global'
}

resource pdzDfs 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.dfs.core.windows.net'
  location: 'global'
}

resource pdzBlobLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: '${namePrefix}-blob-link'
  parent: pdzBlob
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource pdzDfsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: '${namePrefix}-dfs-link'
  parent: pdzDfs
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource pdzgBlob 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'default'
  parent: peBlob
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: {
          privateDnsZoneId: pdzBlob.id
        }
      }
    ]
  }
}

resource pdzgDfs 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'default'
  parent: peDfs
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'dfs'
        properties: {
          privateDnsZoneId: pdzDfs.id
        }
      }
    ]
  }
}

// -------------------------
// Synapse Workspace (Serverless only path) + SQL Private Endpoints
// -------------------------
resource syn 'Microsoft.Synapse/workspaces@2021-06-01' = {
  name: '${projectName}synapse${environment}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    defaultDataLakeStorage: {
      accountUrl: 'https://${sa.name}.dfs.core.windows.net'
      filesystem: 'data'
    }
    managedVirtualNetwork: 'default'
    publicNetworkAccess: 'Disabled'
    sqlAdministratorLogin: 'sqladmin'
    sqlAdministratorLoginPassword: 'UseKeyVaultOrAADOnly!'
  }
}

resource peSynSql 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-syn-sql-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'syn-sql'
        properties: {
          privateLinkServiceId: syn.id
          groupIds: [
            'Sql'
          ]
        }
      }
      {
        name: 'syn-ondemand'
        properties: {
          privateLinkServiceId: syn.id
          groupIds: [
            'SqlOnDemand'
          ]
        }
      }
    ]
  }
}

resource pdzSyn 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.sql.azuresynapse.net'
  location: 'global'
}

resource pdzSynLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: '${namePrefix}-syn-link'
  parent: pdzSyn
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource pdzgSyn 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'default'
  parent: peSynSql
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'syn'
        properties: {
          privateDnsZoneId: pdzSyn.id
        }
      }
    ]
  }
}

// -------------------------
// Content Safety (Cognitive Services) + PE
// -------------------------
resource safety 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: '${projectName}-safety-${environment}'
  location: location
  tags: tags
  kind: 'ContentSafety'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: '${projectName}-safety-${environment}'
    publicNetworkAccess: 'Disabled'
  }
}

resource peSafety 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-safety-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'safety'
        properties: {
          privateLinkServiceId: safety.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource pdzCog 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
}

resource pdzCogLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: '${namePrefix}-cog-link'
  parent: pdzCog
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource pdzgSafety 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'default'
  parent: peSafety
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cog'
        properties: {
          privateDnsZoneId: pdzCog.id
        }
      }
    ]
  }
}

// -------------------------
// Front Door -> APIM routing with Private Link
// -------------------------
resource peApim 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: '${namePrefix}-apim-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, 'private-endpoints-subnet')
    }
    privateLinkServiceConnections: [
      {
        name: 'apim'
        properties: {
          privateLinkServiceId: apim.id
          groupIds: [
            'Gateway'
          ]
        }
      }
    ]
  }
}

resource afdOg 'Microsoft.Cdn/profiles/originGroups@2023-05-01' = {
  name: 'apim-group'
  parent: afdProfile
  properties: {
    loadBalancingSettings: {
      sampleSize: 4
      successfulSamplesRequired: 3
      additionalLatencyInMilliseconds: 0
    }
    healthProbeSettings: {
      probeRequestType: 'HEAD'
      probeProtocol: 'Http'
      probeIntervalInSeconds: 30
      probePath: '/'
    }
  }
}

resource afdOrigin 'Microsoft.Cdn/profiles/originGroups/origins@2023-05-01' = {
  name: 'apim-origin'
  parent: afdOg
  properties: {
    hostName: apim.properties.gatewayUrl
    originHostHeader: apim.properties.gatewayUrl
    enabledState: 'Enabled'
    httpPort: 80
    httpsPort: 443
    privateLink: {
      privateLinkResourceId: apim.id
      location: location
      requestMessage: 'AFD -> APIM'
      groupId: 'Gateway'
    }
  }
}

resource afdRoute 'Microsoft.Cdn/profiles/afdEndpoints/routes@2023-05-01' = {
  name: 'api-route'
  parent: afdEndpoint
  properties: {
    originGroup: {
      id: afdOg.id
    }
    httpsRedirect: 'Enabled'
    supportedProtocols: [
      'Https'
    ]
    patternsToMatch: [
      '/v1/*'
      '/query'
      '/health'
    ]
    forwardingProtocol: 'MatchRequest'
    linkToDefaultDomain: 'Enabled'
  }
}

// -------------------------
// RBAC for data-plane access
// -------------------------
resource aoaiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ca.id, aoai.id, 'aoai-user')
  scope: aoai
  properties: {
    principalId: ca.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
  }
}

resource searchDataContrib 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ca.id, search.id, 'search-data-contrib')
  scope: search
  properties: {
    principalId: ca.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0')
  }
}

// -------------------------
// Diagnostic Settings
// -------------------------
resource diagApim 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-apim'
  scope: apim
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(apim.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(apim.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagAfd 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-afd'
  scope: afdProfile
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(afdProfile.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(afdProfile.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagCae 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-cae'
  scope: cae
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(cae.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(cae.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagCa 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-ca'
  scope: ca
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(ca.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(ca.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagAoai 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-aoai'
  scope: aoai
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(aoai.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(aoai.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagSearch 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-search'
  scope: search
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(search.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(search.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagCosmos 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-cosmos'
  scope: cosmos
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(cosmos.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(cosmos.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagSyn 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-syn'
  scope: syn
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(syn.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(syn.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagStorage 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-storage'
  scope: sa
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(sa.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(sa.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagRedisEnt 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (useRedisEnterprise) {
  name: 'diag-redis-ent'
  scope: redisEnt
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(redisEnt.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(redisEnt.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

resource diagRedisStd 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!useRedisEnterprise) {
  name: 'diag-redis-std'
  scope: redisStd
  properties: {
    workspaceId: logws.id
    logs: [
      for c in listDiagnosticSettingsCategory(redisStd.id, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ]
    metrics: [
      for m in listDiagnosticSettingsCategory(redisStd.id, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ]
  }
}

// -------------------------
// Outputs
// -------------------------
output frontDoorEndpoint string = afdEndpoint.properties.hostName
output apimGatewayUrl string = apim.properties.gatewayUrl
output openaiEndpoint string = aoai.properties.endpoint
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output appInsightsConnectionString string = appins.properties.ConnectionString
