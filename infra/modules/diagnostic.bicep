// infra/modules/diagnostic.bicep
// Attach diagnostic settings to the resource scope where this module is invoked.

@description('Log Analytics workspace resource id')
param workspaceId string

@description('Diagnostic settings name')
param name string = 'to-la'

@description('Enable log categories discovered at deploy time')
param enableLogs bool = true

@description('Enable metric categories discovered at deploy time')
param enableMetrics bool = true

var targetResourceId = scope().resourceId

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: name
  scope: scope()
  properties: {
    workspaceId: workspaceId
    logs: enableLogs ? [
      for c in listDiagnosticSettingsCategory(targetResourceId, '2021-05-01-preview').value: {
        category: c.name
        enabled: true
        retentionPolicy: {
          days: 0
          enabled: false
        }
      }
    ] : []
    metrics: enableMetrics ? [
      for m in listDiagnosticSettingsCategory(targetResourceId, '2021-05-01-preview').value
        where (m.categoryType == 'Metrics'): {
          category: m.name
          enabled: true
          retentionPolicy: {
            days: 0
            enabled: false
          }
        }
    ] : []
  }
}
