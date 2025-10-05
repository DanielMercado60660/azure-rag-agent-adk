#!/bin/bash
set -e

# Azure RAG Agent Deployment Script
# This script deploys the complete Azure RAG Agent infrastructure and application

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
PROJECT_NAME="ragagent"
ENVIRONMENT="prod"
LOCATION="eastus"
RESOURCE_GROUP=""
ACR_NAME=""
USE_REDIS_ENTERPRISE=true
SYNAPSE_SERVERLESS_ONLY=true

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy Azure RAG Agent infrastructure and application

OPTIONS:
    -g, --resource-group     Azure resource group name (required)
    -r, --acr-name          Azure Container Registry name (required)
    -p, --project-name      Project name (default: ragent)
    -e, --environment       Environment name (default: prod)
    -l, --location          Azure region (default: eastus)
    -h, --help              Show this help message

EXAMPLES:
    $0 -g my-rg -r myacr
    $0 -g my-rg -r myacr -p myproject -e dev -l westus2

PREREQUISITES:
    - Azure CLI installed and logged in
    - Docker installed
    - Bicep CLI installed (for infrastructure deployment)
    - Sufficient Azure permissions to create resources

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -g|--resource-group)
            RESOURCE_GROUP="$2"
            shift 2
            ;;
        -r|--acr-name)
            ACR_NAME="$2"
            shift 2
            ;;
        -p|--project-name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -l|--location)
            LOCATION="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$RESOURCE_GROUP" || -z "$ACR_NAME" ]]; then
    print_error "Resource group and ACR name are required"
    show_usage
    exit 1
fi

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Azure CLI
    if ! command -v az &> /dev/null; then
        print_error "Azure CLI is not installed"
        exit 1
    fi
    
    # Check if logged in to Azure
    if ! az account show &> /dev/null; then
        print_error "Not logged in to Azure. Please run 'az login'"
        exit 1
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    # Check Bicep
    if ! command -v bicep &> /dev/null; then
        print_warning "Bicep CLI not found. Installing..."
        az bicep install
    fi
    
    print_success "Prerequisites check passed"
}

# Deploy infrastructure
deploy_infrastructure() {
    print_status "Deploying Azure infrastructure..."
    
    # Create resource group if it doesn't exist
    if ! az group show --name "$RESOURCE_GROUP" &> /dev/null; then
        print_status "Creating resource group: $RESOURCE_GROUP"
        az group create --name "$RESOURCE_GROUP" --location "$LOCATION"
    else
        print_status "Resource group $RESOURCE_GROUP already exists"
    fi
    
    # Deploy Bicep template
    print_status "Deploying infrastructure with Bicep..."
    az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file infra/main.bicep \
        --parameters \
            projectName="$PROJECT_NAME" \
            environment="$ENVIRONMENT" \
            location="$LOCATION" \
            useRedisEnterprise="$USE_REDIS_ENTERPRISE" \
            synapseServerlessOnly="$SYNAPSE_SERVERLESS_ONLY" \
        --verbose
    
    print_success "Infrastructure deployment completed"
}

# Build and push container image
build_and_push_image() {
    print_status "Building and pushing container image..."
    
    # Get ACR login server
    ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query "loginServer" -o tsv)
    
    # Login to ACR
    print_status "Logging in to Azure Container Registry..."
    az acr login --name "$ACR_NAME"
    
    # Build and push image
    print_status "Building Docker image..."
    az acr build \
        --registry "$ACR_NAME" \
        --image "azure-rag-agent:latest" \
        --image "azure-rag-agent:$(date +%Y%m%d-%H%M%S)" \
        ./App
    
    print_success "Container image built and pushed successfully"
}

# Deploy to Container Apps
deploy_container_app() {
    print_status "Deploying to Azure Container Apps..."
    
    # Get infrastructure outputs
    FRONT_DOOR_ENDPOINT=$(az deployment group show \
        --resource-group "$RESOURCE_GROUP" \
        --name "main" \
        --query "properties.outputs.frontDoorEndpoint.value" -o tsv)
    
    APP_INSIGHTS_CONNECTION_STRING=$(az deployment group show \
        --resource-group "$RESOURCE_GROUP" \
        --name "main" \
        --query "properties.outputs.appInsightsConnectionString.value" -o tsv)
    
    # Update container app with new image
    print_status "Updating Container App with new image..."
    az containerapp update \
        --name "${PROJECT_NAME}-api-${ENVIRONMENT}" \
        --resource-group "$RESOURCE_GROUP" \
        --image "${ACR_NAME}.azurecr.io/azure-rag-agent:latest" \
        --set-env-vars \
            APPLICATIONINSIGHTS_CONNECTION_STRING="$APP_INSIGHTS_CONNECTION_STRING" \
            PROJECT_ENV="$ENVIRONMENT"
    
    print_success "Container App deployment completed"
}

# Run post-deployment setup
post_deployment_setup() {
    print_status "Running post-deployment setup..."
    
    # Get resource names
    SEARCH_NAME="${PROJECT_NAME}-search-${ENVIRONMENT}"
    COSMOS_NAME="${PROJECT_NAME}-cosmos-${ENVIRONMENT}"
    OPENAI_NAME="${PROJECT_NAME}-openai-${ENVIRONMENT}"
    
    # Get endpoints
    SEARCH_ENDPOINT="https://${SEARCH_NAME}.search.windows.net"
    COSMOS_ENDPOINT="https://${COSMOS_NAME}.documents.azure.com:443/"
    OPENAI_ENDPOINT="https://${OPENAI_NAME}.openai.azure.com/"
    
    print_status "Setting up AI Search index..."
    python scripts/setup_search.py \
        --endpoint "$SEARCH_ENDPOINT" \
        --index-name "acme-corp-kb" \
        --verbose
    
    print_status "Setting up Cosmos DB containers..."
    python scripts/setup_cosmos.py \
        --resource-group "$RESOURCE_GROUP" \
        --account-name "$COSMOS_NAME" \
        --endpoint "$COSMOS_ENDPOINT" \
        --sql-container "acme-corp-documents" \
        --graph "acme-corp-graph" \
        --verbose
    
    print_status "Loading sample data..."
    python scripts/load_data.py \
        --tenant-id "acme-corp" \
        --documents "./samples/tenant-acme-corp" \
        --search-endpoint "$SEARCH_ENDPOINT" \
        --search-index "acme-corp-kb" \
        --cosmos-endpoint "$COSMOS_ENDPOINT" \
        --cosmos-container "acme-corp-documents" \
        --aoai-endpoint "$OPENAI_ENDPOINT" \
        --aoai-deployment "text-embedding-3-small" \
        --verbose
    
    print_success "Post-deployment setup completed"
}

# Run smoke tests
run_smoke_tests() {
    print_status "Running smoke tests..."
    
    # Get the front door endpoint
    FRONT_DOOR_ENDPOINT=$(az deployment group show \
        --resource-group "$RESOURCE_GROUP" \
        --name "main" \
        --query "properties.outputs.frontDoorEndpoint.value" -o tsv)
    
    # Wait for deployment to be ready
    print_status "Waiting for deployment to be ready..."
    sleep 30
    
    # Test health endpoint
    print_status "Testing health endpoint..."
    if curl -f "https://$FRONT_DOOR_ENDPOINT/health" > /dev/null 2>&1; then
        print_success "Health check passed"
    else
        print_error "Health check failed"
        exit 1
    fi
    
    # Test query endpoint (basic smoke test)
    print_status "Testing query endpoint..."
    if curl -f -X POST "https://$FRONT_DOOR_ENDPOINT/query" \
        -H "Content-Type: application/json" \
        -d '{"query": "What is our company revenue?", "tenant_id": "acme-corp"}' \
        > /dev/null 2>&1; then
        print_success "Query endpoint test passed"
    else
        print_warning "Query endpoint test failed (this might be expected if no data is loaded)"
    fi
    
    print_success "Smoke tests completed"
}

# Main deployment function
main() {
    print_status "Starting Azure RAG Agent deployment..."
    print_status "Project: $PROJECT_NAME"
    print_status "Environment: $ENVIRONMENT"
    print_status "Resource Group: $RESOURCE_GROUP"
    print_status "Location: $LOCATION"
    print_status "ACR: $ACR_NAME"
    
    # Run deployment steps
    check_prerequisites
    deploy_infrastructure
    build_and_push_image
    deploy_container_app
    post_deployment_setup
    run_smoke_tests
    
    # Get final endpoints
    FRONT_DOOR_ENDPOINT=$(az deployment group show \
        --resource-group "$RESOURCE_GROUP" \
        --name "main" \
        --query "properties.outputs.frontDoorEndpoint.value" -o tsv)
    
    print_success "Deployment completed successfully!"
    print_status "Front Door Endpoint: https://$FRONT_DOOR_ENDPOINT"
    print_status "Health Check: https://$FRONT_DOOR_ENDPOINT/health"
    print_status "API Documentation: https://$FRONT_DOOR_ENDPOINT/docs"
    
    cat << EOF

🎉 Azure RAG Agent is now deployed and ready!

Next steps:
1. Test the API: curl -X POST "https://$FRONT_DOOR_ENDPOINT/query" \\
   -H "Content-Type: application/json" \\
   -d '{"query": "What is our Q4 revenue?", "tenant_id": "acme-corp"}'

2. Monitor the application in Azure Portal
3. Check logs in Application Insights
4. Import the monitoring workbook from monitor/workbook.json

For more information, see the README.md file.

EOF
}

# Run main function
main "$@"
