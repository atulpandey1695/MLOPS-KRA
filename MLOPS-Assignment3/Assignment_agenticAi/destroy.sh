#!/bin/bash

# =============================================================================
# Destroy Script for LangGraph AI Agents
# =============================================================================
# This script removes all deployed resources from Minikube
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

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  LangGraph AI Agents - Destroy Script${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Confirm destruction
echo -e "${YELLOW}This will remove:${NC}"
echo "  - Kubernetes Deployment"
echo "  - Kubernetes Service"
echo "  - Kubernetes ConfigMap"
echo "  - Kubernetes Secret"
echo "  - Docker image from Minikube"
echo ""

read -p "Are you sure you want to proceed? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Destroy operation cancelled.${NC}"
    exit 0
fi

# Point docker to minikube
eval $(minikube docker-env)

# Delete Kubernetes resources
echo -e "${YELLOW}[1/4] Removing Kubernetes resources...${NC}"

# Delete Service
if kubectl get svc $SERVICE_NAME &> /dev/null; then
    kubectl delete svc $SERVICE_NAME
    echo -e "${GREEN}✓ Service deleted${NC}"
else
    echo -e "${YELLOW}  Service not found, skipping...${NC}"
fi

# Delete Deployment
if kubectl get deployment $DEPLOYMENT_NAME &> /dev/null; then
    kubectl delete deployment $DEPLOYMENT_NAME
    echo -e "${GREEN}✓ Deployment deleted${NC}"
else
    echo -e "${YELLOW}  Deployment not found, skipping...${NC}"
fi

# Delete ConfigMap
if kubectl get configmap assignment-agentic-ai-config &> /dev/null; then
    kubectl delete configmap assignment-agentic-ai-config
    echo -e "${GREEN}✓ ConfigMap deleted${NC}"
else
    echo -e "${YELLOW}  ConfigMap not found, skipping...${NC}"
fi

# Delete Secret
if kubectl get secret assignment-agentic-ai-secret &> /dev/null; then
    kubectl delete secret assignment-agentic-ai-secret
    echo -e "${GREEN}✓ Secret deleted${NC}"
else
    echo -e "${YELLOW}  Secret not found, skipping...${NC}"
fi

# Remove Docker image
echo -e "${YELLOW}[2/4] Removing Docker image...${NC}"
if docker images -q $IMAGE_NAME &> /dev/null; then
    docker rmi $IMAGE_NAME
    echo -e "${GREEN}✓ Docker image removed${NC}"
else
    echo -e "${YELLOW}  Docker image not found, skipping...${NC}"
fi

# Kill port-forward processes
echo -e "${YELLOW][3/4] Cleaning up port-forward processes...${NC}"
pkill -f "kubectl port-forward.*$SERVICE_NAME" 2>/dev/null || true
echo -e "${GREEN}✓ Port-forward processes cleaned up${NC}"

# Check for remaining pods
echo -e "${YELLOW}[4/4] Checking for remaining pods...${NC}"
REMAINING_PODS=$(kubectl get pods -l app=assignment-agentic-ai 2>/dev/null | grep -v "NAME" | wc -l)
if [ "$REMAINING_PODS" -gt 0 ]; then
    echo -e "${YELLOW}  Found $REMAINING_PODS remaining pods, forcing deletion...${NC}"
    kubectl delete pods -l app=assignment-agentic-ai --grace-period=0 --force 2>/dev/null || true
fi
echo -e "${GREEN}✓ Cleanup complete${NC}"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Destroy Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# Show remaining resources
echo -e "${BLUE}Remaining resources:${NC}"
echo ""
kubectl get all 2>/dev/null | grep -v "No resources found" || echo "  No resources in namespace"
echo ""

echo -e "${GREEN}All resources have been removed.${NC}"
echo -e "${YELLOW}To completely remove Minikube, run:${NC}"
echo "  minikube delete"
echo ""