#!/bin/bash

# =============================================================================
# Deploy Script for LangGraph AI Agents
# =============================================================================
# This script deploys the five LangGraph AI agents to Minikube
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="default"
DEPLOYMENT_NAME="assignment-agentic-ai-deployment"
SERVICE_NAME="assignment-agentic-ai-service"
IMAGE_NAME="assignment-agentic-ai:latest"
PORT=8080

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  LangGraph AI Agents - Deploy Script${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}[1/7] Checking prerequisites...${NC}"

if ! command -v minikube &> /dev/null; then
    echo -e "${RED}ERROR: minikube is not installed${NC}"
    exit 1
fi

if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}ERROR: kubectl is not installed${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: docker is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites are installed${NC}"

# Check if .env file exists
echo -e "${YELLOW}[2/7] Checking environment configuration...${NC}"

if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found in current directory${NC}"
    echo -e "${YELLOW}Please create .env file with OPENAI_API_KEY${NC}"
    exit 1
fi

set -a
source ./.env
set +a

if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}ERROR: OPENAI_API_KEY is missing in .env${NC}"
    exit 1
fi

OPENAI_API_BASE="${OPENAI_API_BASE:-https://openrouter.ai/api/v1}"

echo -e "${GREEN}✓ .env file found${NC}"

# Start Minikube if not running
echo -e "${YELLOW}[3/7] Checking Minikube status...${NC}"

if ! minikube status &> /dev/null; then
    echo -e "${YELLOW}Starting Minikube...${NC}"
    minikube start
else
    echo -e "${GREEN}✓ Minikube is running${NC}"
fi

# Point docker to minikube
echo -e "${YELLOW}[4/7] Configuring Docker to use Minikube...${NC}"
eval $(minikube docker-env)
echo -e "${GREEN}✓ Docker configured for Minikube${NC}"

# Build Docker image
echo -e "${YELLOW}[5/7] Building Docker image...${NC}"
docker build -t $IMAGE_NAME . --no-cache
echo -e "${GREEN}✓ Docker image built successfully${NC}"

# Apply Kubernetes manifests
echo -e "${YELLOW}[6/7] Deploying to Kubernetes...${NC}"

# Create Secret from .env so credentials are not stored in the image or manifest.
kubectl create secret generic assignment-agentic-ai-secret \
    --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
    --from-literal=OPENAI_API_BASE="$OPENAI_API_BASE" \
    --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Secret applied from .env${NC}"

# Apply ConfigMap
kubectl apply -f k8s/configmap.yaml
echo -e "${GREEN}✓ ConfigMap applied${NC}"

# Apply Deployment
kubectl apply -f k8s/deployment.yaml
echo -e "${GREEN}✓ Deployment applied${NC}"

# Apply Service
kubectl apply -f k8s/service.yaml
echo -e "${GREEN}✓ Service applied${NC}"

# Wait for deployment
echo -e "${YELLOW}[7/7] Waiting for deployment to be ready...${NC}"
kubectl rollout status deployment/$DEPLOYMENT_NAME --timeout=120s

# Show status
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# Get pod status
echo -e "${BLUE}Pod Status:${NC}"
kubectl get pods -l app=assignment-agentic-ai
echo ""

# Get service info
echo -e "${BLUE}Service Status:${NC}"
kubectl get svc $SERVICE_NAME
echo ""

# Get access instructions
echo -e "${GREEN}To access the API, run:${NC}"
echo ""
echo "  kubectl port-forward svc/$SERVICE_NAME $PORT:80 &"
echo ""
echo -e "${GREEN}Then access at:${NC}"
echo "  http://localhost:$PORT"
echo ""

# Test the API
echo -e "${YELLOW}Testing API endpoints...${NC}"
echo ""

kubectl port-forward svc/$SERVICE_NAME $PORT:80 >/tmp/${SERVICE_NAME}-port-forward.log 2>&1 &
PORT_FORWARD_PID=$!
trap 'kill $PORT_FORWARD_PID 2>/dev/null || true' EXIT
sleep 5

HEALTH_RESPONSE=$(curl -s http://localhost:$PORT/health)
if [[ "$HEALTH_RESPONSE" == *"healthy"* ]]; then
    echo -e "${GREEN}✓ Health endpoint is responding${NC}"
else
    echo -e "${RED}ERROR: Health endpoint check failed${NC}"
    exit 1
fi

# Test Agent Bot
echo -e "${BLUE}Testing Agent Bot:${NC}"
RESPONSE=$(curl -s -X POST http://localhost:$PORT/api/agent-bot/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}' 2>/dev/null || true)

if [[ "$RESPONSE" == *"Hello"* ]] || [[ "$RESPONSE" == *"response"* ]]; then
    echo -e "${GREEN}✓ Agent Bot is responding${NC}"
else
    echo -e "${YELLOW}⚠ Agent Bot test did not return an expected response${NC}"
    echo -e "${YELLOW}  Raw response:${NC} $RESPONSE"
fi

echo ""
echo -e "${GREEN}Deployment completed successfully!${NC}"