# Azure RAG Agent with ADK

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Azure](https://img.shields.io/badge/azure-ready-blue.svg)](https://azure.microsoft.com)
[![ADK](https://img.shields.io/badge/google-adk-compliant-green.svg)](https://google.github.io/adk-docs/)
[![Elephant](https://img.shields.io/badge/🐘-intelligent%20memory-blue.svg)](https://github.com/DanielMercado60660/azure-rag-agent-adk)


Hi Rami & Saher!

This is an example implementation of an advanced multi-tenant Retrieval-Augmented Generation (RAG) agent built with **Google Agent Development Kit (ADK)** and Azure services.

![Azure RAG Agent with ADK](./assets/AzureADKLebElephant.png)


## Overview

This is an example implementation of an advanced RAG agent that demonstrates how to build a sophisticated retrieval system using multiple data sources. The agent dynamically selects optimal workflow patterns based on query complexity:

- **Sequential Pipeline** - For simple, direct queries
- **Parallel Fan-Out/Gather** - For medium complexity with concurrent tool execution
- **Iterative Refinement** - For complex queries requiring quality loops

## Key Features

✅ **ADK-Compliant Architecture** - Follows official Google ADK patterns for multi-agent orchestration
✅ **LiteLLM Integration** - Uses ADK's LiteLLM wrapper for Azure OpenAI with Entra ID auth
✅ **Multi-Source Retrieval** - Combines vector search, SQL analytics, graph traversal, and web search
✅ **Azure Native** - AI Search (semantic ranking), Cosmos Gremlin, Synapse SQL, OpenAI
✅ **Business Features** - Multi-tenancy, budget tracking, circuit breakers, caching, content safety

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Azure subscription with resources provisioned (see `infra/main.bicep`)
- Azure services: OpenAI, AI Search, Cosmos DB, Redis, Synapse, Content Safety

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/azure-rag-agent-adk.git
cd azure-rag-agent-adk

# Install dependencies
pip install -r App/requirements.txt

# Copy environment template
cp env.template .env
# Edit .env with your Azure service endpoints
```

### Run Locally

```bash
cd App
uvicorn agent:app --reload --host 0.0.0.0 --port 8080
```

### Test the API

```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is our Q4 revenue?",
    "tenant_id": "acme-corp",
    "user_tier": "enterprise"
  }'
```

## Architecture

For detailed architecture diagrams and system design, see [ARCHITECTURE.md](./docs/ARCHITECTURE.md).

### Workflow Selection

```
Query → Classifier (LLM) → Complexity Assessment
                              ↓
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
    Simple              Medium                 Complex
        ↓                     ↓                     ↓
  Sequential         Parallel Tools        Iterative Loop
   Pipeline          Fan-Out/Gather        (max 3 iterations)
```

### Agent Types

**LLM Agents** (Reasoning):
- Classifier - Query intent/complexity/domain
- Planner - Execution strategy
- Synthesizer - Final response generation
- Reflector - Quality evaluation

**Workflow Agents** (Orchestration):
- ToolExecutionAgent - Tool execution with budgets/circuit breakers
- QualityGateAgent - Deterministic quality checks
- QualityCheckerAgent - Loop escalation control

### Retrieval Tools

- **Azure AI Search** - Hybrid vector + BM25 + semantic ranking
- **Cosmos Gremlin** - Graph traversal for relationships
- **Synapse SQL** - Analytics queries
- **Web Search** - Current information via Bing

## ⚙️ Configuration

### Environment Variables

Copy `env.template` to `.env` and configure your Azure services:

```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com/
AZURE_GPT4O_DEPLOYMENT=gpt-4o
AZURE_GPT4O_MINI_DEPLOYMENT=gpt-4o-mini

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://your-search.search.windows.net

# Redis Cache
AZURE_REDIS_HOST=your-redis.redis.cache.windows.net

# See env.template for complete configuration
```

**Important**: Configure semantic ranker in your AI Search index with a semantic configuration named "default" for optimal sentiment analysis.

## Deployment

### Docker

```bash
# Build
docker build -t azure-rag-agent:latest ./App

# Run
docker run -p 8080:8080 \
  -e OPENAI_ENDPOINT="..." \
  -e SEARCH_ENDPOINT="..." \
  azure-rag-agent:latest
```

### Azure Container Apps

```bash
# Build and push to ACR
az acr build --registry <your-acr> --image azure-rag-agent:latest ./App

# Deploy
az containerapp update \
  --name rag-agent \
  --resource-group <rg> \
  --image <your-acr>.azurecr.io/azure-rag-agent:latest
```

## 📁 Project Structure

```
azure-rag-adk/
├── App/                      # Main application code
│   ├── agent.py              # ADK agent entry point (67 lines)
│   ├── config/               # Configuration and settings
│   ├── core/                 # Infrastructure (clients, cache, etc.)
│   ├── tools/                # ADK BaseTool implementations
│   ├── agents/                # ADK agent factories
│   ├── workflows/             # ADK workflow patterns
│   ├── safety/               # Content safety validation
│   ├── api/                   # FastAPI application
│   ├── Dockerfile            # Container build
│   └── requirements.txt      # Python dependencies
├── scripts/                   # Deployment and setup scripts
├── tests/                     # Test suite
├── infra/                     # Azure infrastructure (Bicep)
├── monitor/                   # Azure Monitor workbooks
├── samples/                   # Sample data and examples
├── docs/                      # Documentation
├── env.template              # Environment configuration template
└── README.md                 # This file
```

## 🛠️ Development

### Local Development Setup

```bash
# Setup local environment
./scripts/setup-local.sh

# Run tests
python -m pytest tests/

# Start development server
cd App && uvicorn agent:app --reload
```

### Adding New Tools

1. Create new tool in `App/tools/` inheriting from `BaseTool`
2. Add to tools dictionary in `App/agent.py`
3. Update agent workflows as needed

### Architecture Patterns

- **ADK Compliance**: All agents follow Google ADK patterns
- **Modular Design**: Clear separation of concerns
- **Business Features**: Circuit breakers, caching, cost tracking, multi-tenancy

## 📊 Monitoring

Import `monitor/workbook.json` to Azure Monitor for insights on:
- API latency and tool timings
- Cache hit rates
- Circuit breaker events
- Cost breakdowns by tool/LLM
- APIM and Front Door metrics

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Google ADK](https://google.github.io/adk-docs/) for the agent development framework
- [Azure AI Services](https://azure.microsoft.com/en-us/products/ai-services) for the AI capabilities
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
