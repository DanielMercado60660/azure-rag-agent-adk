#!/bin/bash
set -e

# Azure RAG Agent - Local Development Setup
# This script sets up the local development environment

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3 is not installed"
        exit 1
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_warning "Docker is not installed (optional for local development)"
    fi
    
    print_success "Prerequisites check completed"
}

# Setup Python environment
setup_python_env() {
    print_status "Setting up Python environment..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        print_status "Creating virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    print_status "Activating virtual environment..."
    source venv/bin/activate
    
    # Install dependencies
    print_status "Installing Python dependencies..."
    cd App
    pip install -r requirements.txt
    cd ..
    
    print_success "Python environment setup completed"
}

# Setup environment variables
setup_env_vars() {
    print_status "Setting up environment variables..."
    
    if [ ! -f ".env" ]; then
        print_status "Creating .env file from template..."
        cp env.template .env
        print_warning "Please update .env file with your actual Azure service endpoints"
    else
        print_status ".env file already exists"
    fi
    
    print_success "Environment variables setup completed"
}

# Run tests
run_tests() {
    print_status "Running tests..."
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Run tests
    cd App
    python -m pytest ../tests/ -v
    cd ..
    
    print_success "Tests completed successfully"
}

# Start development server
start_dev_server() {
    print_status "Starting development server..."
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Start the server
    cd App
    print_status "Starting server on http://localhost:8080"
    print_status "Health check: http://localhost:8080/health"
    print_status "API docs: http://localhost:8080/docs"
    print_status "Press Ctrl+C to stop the server"
    
    python -m uvicorn agent:app --reload --host 0.0.0.0 --port 8080
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [COMMAND]

Local development setup for Azure RAG Agent

COMMANDS:
    setup       Set up the development environment
    test        Run tests
    start       Start the development server
    help        Show this help message

EXAMPLES:
    $0 setup
    $0 test
    $0 start

EOF
}

# Main function
main() {
    case "${1:-setup}" in
        setup)
            print_status "Setting up Azure RAG Agent development environment..."
            check_prerequisites
            setup_python_env
            setup_env_vars
            print_success "Development environment setup completed!"
            print_status "Next steps:"
            print_status "1. Update .env file with your Azure service endpoints"
            print_status "2. Run '$0 test' to run tests"
            print_status "3. Run '$0 start' to start the development server"
            ;;
        test)
            print_status "Running tests..."
            check_prerequisites
            run_tests
            ;;
        start)
            print_status "Starting development server..."
            check_prerequisites
            start_dev_server
            ;;
        help)
            show_usage
            ;;
        *)
            print_error "Unknown command: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
