# Azure RAG Agent API Documentation

## Overview

The Azure RAG Agent provides a production-grade Retrieval-Augmented Generation (RAG) API built with Google Agent Development Kit (ADK) and Azure services. It dynamically selects optimal workflow patterns based on query complexity and implements enterprise patterns including budget tracking, circuit breakers, caching, and content safety.

## Base URL

```
https://your-front-door-endpoint.azurefd.net
```

## Authentication

The API uses Azure AD authentication via JWT tokens. Include the token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

## Endpoints

### POST /query

Main query endpoint for RAG processing. The agent will automatically classify the query complexity and select the appropriate workflow pattern.

#### Request Body

```json
{
  "query": "What is our Q4 revenue?",
  "tenant_id": "acme-corp",
  "session_id": "optional-session-id",
  "user_tier": "enterprise"
}
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | The natural language query to process |
| `tenant_id` | string | Yes | Tenant identifier for multi-tenant isolation |
| `session_id` | string | No | Optional session ID for conversation context |
| `user_tier` | string | No | User tier for budget limits (free, pro, enterprise) |

#### Response

```json
{
  "answer": "Based on the financial data, your Q4 2024 revenue was $125.3M, representing a 15% year-over-year growth. This includes $43.9M from AcmeCRM Pro, $31.3M from AcmeAI Platform, $35.1M from AcmeCloud Suite, and $15.0M from Professional Services.",
  "sources": [
    {
      "tool": "azure_ai_search",
      "count": 5,
      "latency_ms": 245,
      "confidence": 0.89,
      "context_items": [
        {
          "type": "text",
          "source": "azure_ai_search",
          "id": "doc-001",
          "content": "Q4 2024 Results: Revenue: $125.3M (up 15% YoY)",
          "metadata": {
            "title": "Financial Reports Q4 2024",
            "source": "financial-reports.txt"
          }
        }
      ]
    },
    {
      "tool": "synapse_sql",
      "count": 3,
      "latency_ms": 1200,
      "confidence": 0.92,
      "context_items": [
        {
          "type": "table-row",
          "source": "synapse_sql",
          "id": "1",
          "content": "Q4_2024, 125300000, 0.15",
          "metadata": {
            "quarter": "Q4_2024",
            "revenue": 125300000,
            "growth_rate": 0.15
          }
        }
      ]
    }
  ],
  "cost": 0.0023,
  "latency_ms": 1250,
  "classification": {
    "intent": "lookup",
    "complexity": "medium",
    "domain": "finance"
  },
  "strategy": {
    "strategy_type": "multi-source",
    "tools": ["azure_ai_search", "synapse_sql"],
    "execution_mode": "parallel",
    "reasoning": "Financial query requires both document search and analytical data"
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The generated response to the query |
| `sources` | array | Array of source information from each tool used |
| `cost` | number | Total cost in USD for processing this query |
| `latency_ms` | number | Total processing time in milliseconds |
| `classification` | object | Query classification results |
| `strategy` | object | Execution strategy used |

#### Source Object

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Name of the tool that provided the data |
| `count` | number | Number of items returned by the tool |
| `latency_ms` | number | Tool execution time in milliseconds |
| `confidence` | number | Average confidence score (0-1) |
| `context_items` | array | Detailed context items from the tool |

#### Error Responses

##### 400 Bad Request
```json
{
  "detail": "Content policy violation: hate: severity 4"
}
```

##### 401 Unauthorized
```json
{
  "detail": "Invalid or missing authentication token"
}
```

##### 429 Too Many Requests
```json
{
  "detail": "Rate limit exceeded. Try again later."
}
```

##### 500 Internal Server Error
```json
{
  "detail": "Internal server error: Tool execution failed"
}
```

### GET /health

Health check endpoint that validates all system dependencies.

#### Response

```json
{
  "status": "healthy",
  "timestamp": 1704067200.123,
  "version": "1.0.0",
  "dependencies": {
    "redis": true,
    "openai": true,
    "search": true
  }
}
```

#### Health Status Values

- `healthy`: All dependencies are operational
- `degraded`: Some dependencies are unavailable but core functionality works

## Workflow Patterns

The agent automatically selects one of three workflow patterns based on query complexity:

### 1. Sequential Pipeline (Simple Queries)
- **Use Case**: Direct fact retrieval, simple lookups
- **Execution**: Linear flow through agents
- **Tools**: Typically 1 tool
- **Budget**: $0.001

### 2. Parallel Fan-Out/Gather (Medium Complexity)
- **Use Case**: Multi-source queries requiring concurrent tool execution
- **Execution**: Tools run in parallel, results gathered
- **Tools**: 2-3 tools typically
- **Budget**: $0.005

### 3. Iterative Refinement (Complex Queries)
- **Use Case**: Complex analysis requiring multiple iterations
- **Execution**: Loop until quality thresholds are met
- **Tools**: 4+ tools with refinement
- **Budget**: $0.010

## Available Tools

### Azure AI Search
- **Purpose**: Hybrid vector + BM25 + semantic ranking
- **Use For**: Document retrieval, semantic search
- **Features**: Reranking, filtering, faceting

### Cosmos Gremlin
- **Purpose**: Graph traversal for relationships
- **Use For**: "Related to", "connected to", "impact of" queries
- **Features**: Natural language to Gremlin conversion

### Synapse SQL
- **Purpose**: Analytics queries and data analysis
- **Use For**: Trends, aggregations, comparisons
- **Features**: Natural language to SQL conversion

### Web Search
- **Purpose**: Current information and external data
- **Use For**: Recent events, news, information beyond knowledge cutoff
- **Features**: Bing search integration

## Rate Limits

| User Tier | Requests per Hour | Requests per Day |
|-----------|-------------------|------------------|
| Free | 100 | 1,000 |
| Pro | 1,000 | 10,000 |
| Enterprise | Unlimited | Unlimited |

## Budget Limits

| Complexity | Max Cost (USD) | Max Tools | Max LLM Calls |
|------------|----------------|-----------|---------------|
| Simple | $0.001 | 1 | 1 |
| Medium | $0.005 | 3 | 2 |
| Complex | $0.010 | 5 | 3 |

## Caching

The API implements multi-layer caching:

- **Response Cache**: 1 hour TTL for exact query matches
- **Tool Cache**: 5-30 minutes TTL depending on tool type
- **Session Cache**: 30 minutes TTL for conversation context

## Content Safety

All responses are checked against Azure AI Content Safety with configurable severity thresholds:

- **Hate**: Severity 0-7
- **Self-harm**: Severity 0-7  
- **Sexual**: Severity 0-7
- **Violence**: Severity 0-7

Responses with severity ≥ 4 are blocked.

## Monitoring

The API provides comprehensive observability:

- **Metrics**: Latency, throughput, error rates
- **Logs**: Structured logging with correlation IDs
- **Traces**: Distributed tracing across all components
- **Costs**: Real-time cost tracking and budget enforcement

## Examples

### Simple Query
```bash
curl -X POST "https://your-endpoint.azurefd.net/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "query": "Who is the CEO?",
    "tenant_id": "acme-corp"
  }'
```

### Complex Query
```bash
curl -X POST "https://your-endpoint.azurefd.net/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "query": "What are the key trends in our Q4 revenue compared to competitors?",
    "tenant_id": "acme-corp",
    "user_tier": "enterprise"
  }'
```

### Session-based Query
```bash
curl -X POST "https://your-endpoint.azurefd.net/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "query": "What about our European operations?",
    "tenant_id": "acme-corp",
    "session_id": "conv-12345"
  }'
```

## SDK Examples

### Python
```python
import requests

def query_rag_agent(query, tenant_id, session_id=None, user_tier="free"):
    url = "https://your-endpoint.azurefd.net/query"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {your_token}"
    }
    data = {
        "query": query,
        "tenant_id": tenant_id,
        "session_id": session_id,
        "user_tier": user_tier
    }
    
    response = requests.post(url, json=data, headers=headers)
    return response.json()

# Example usage
result = query_rag_agent(
    query="What is our Q4 revenue?",
    tenant_id="acme-corp",
    user_tier="enterprise"
)
print(result["answer"])
```

### JavaScript
```javascript
async function queryRAGAgent(query, tenantId, sessionId = null, userTier = "free") {
    const response = await fetch("https://your-endpoint.azurefd.net/query", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${yourToken}`
        },
        body: JSON.stringify({
            query,
            tenant_id: tenantId,
            session_id: sessionId,
            user_tier: userTier
        })
    });
    
    return await response.json();
}

// Example usage
const result = await queryRAGAgent(
    "What is our Q4 revenue?",
    "acme-corp",
    null,
    "enterprise"
);
console.log(result.answer);
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Ensure your JWT token is valid and not expired
   - Check that the token has the correct audience and issuer

2. **Rate Limit Exceeded**
   - Implement exponential backoff
   - Consider upgrading to a higher tier

3. **Content Policy Violations**
   - Review your query for potentially harmful content
   - Adjust content safety thresholds if needed

4. **Tool Failures**
   - Check that all Azure services are properly configured
   - Verify network connectivity and permissions

### Debug Mode

Enable debug logging by setting the `LOG_LEVEL` environment variable to `DEBUG`:

```bash
export LOG_LEVEL=DEBUG
```

This will provide detailed information about:
- Query classification
- Tool execution
- Cost tracking
- Cache hits/misses
- Circuit breaker states

## Support

For technical support and questions:

- **Documentation**: See README.md and CLAUDE.md
- **Issues**: Create an issue in the GitHub repository
- **Monitoring**: Check Azure Monitor dashboards
- **Logs**: Review Application Insights logs
