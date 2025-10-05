# Observability Pack — How to wire into your template

This folder contains:
- `infra/modules/diagnostic.bicep`: a reusable module that attaches Diagnostic Settings to a resource and streams logs/metrics to Log Analytics.
- `monitor/workbook.json`: an Azure Monitor Workbook with KQL for API latency, tool timings, cache hit rate, circuit breaker events, costs, APIM & Front Door.

## 1) Import the module
In your main Bicep (after all resources are declared), add calls like:

```bicep
// examples — adjust names to match your resources
module diagApim './infra/modules/diagnostic.bicep' = {
  name: 'diag-apim'
  params: {
    targetResourceId: apim.id
    workspaceId: logAnalytics.id
  }
}

module diagFrontDoor './infra/modules/diagnostic.bicep' = {
  name: 'diag-frontdoor'
  params: {
    targetResourceId: frontDoor.id
    workspaceId: logAnalytics.id
  }
}

module diagContainerApp './infra/modules/diagnostic.bicep' = {
  name: 'diag-containerapp'
  params: {
    targetResourceId: containerApp.id
    workspaceId: logAnalytics.id
  }
}

module diagOpenAI './infra/modules/diagnostic.bicep' = {
  name: 'diag-openai'
  params: {
    targetResourceId: openai.id
    workspaceId: logAnalytics.id
  }
}

module diagSearch './infra/modules/diagnostic.bicep' = {
  name: 'diag-search'
  params: {
    targetResourceId: searchService.id
    workspaceId: logAnalytics.id
  }
}

module diagCosmos './infra/modules/diagnostic.bicep' = {
  name: 'diag-cosmos'
  params: {
    targetResourceId: cosmosAccount.id
    workspaceId: logAnalytics.id
  }
}

module diagRedis './infra/modules/diagnostic.bicep' = {
  name: 'diag-redis'
  params: {
    targetResourceId: redis.id
    workspaceId: logAnalytics.id
  }
}

module diagSynapse './infra/modules/diagnostic.bicep' = {
  name: 'diag-synapse'
  params: {
    targetResourceId: synapseWorkspace.id
    workspaceId: logAnalytics.id
  }
}

module diagKeyVault './infra/modules/diagnostic.bicep' = {
  name: 'diag-kv'
  params: {
    targetResourceId: keyVault.id
    workspaceId: logAnalytics.id
  }
}
```

## 2) App logs for the workbook
Ensure your app emits the following (already suggested in code):
- `emit_event("tool_success", {...})` → goes to `traces`
- `logger.info('cost_meter {...}')` with a JSON blob
- cache hits/misses messages: `Cache hit for ...` and `Cache miss for ...`

## 3) Import the workbook
Portal → Azure Monitor → Workbooks → Import → pick `monitor/workbook.json`.
Edit the Workbook parameter for your workspace if the fallback resource id is empty.
