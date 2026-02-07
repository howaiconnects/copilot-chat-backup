#!/bin/bash
#
# Complete Vector Search Setup Script
# Integrates Azure AI Foundry, Qdrant, and monitoring stack
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Copilot Chat Backup - Vector Search Setup${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ All prerequisites met${NC}\n"

# Install Python dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
pip3 install -q qdrant-client openai langchain langchain-openai langchain-qdrant
echo -e "${GREEN}✅ Python dependencies installed${NC}\n"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file...${NC}"
    
    # Prompt for Azure AI Foundry credentials
    read -p "Enter your Azure OpenAI API Key: " AZURE_API_KEY
    read -p "Enter your Azure OpenAI Endpoint: " AZURE_ENDPOINT
    read -p "Enter your Azure OpenAI Deployment name [text-embedding-3-small]: " AZURE_DEPLOYMENT
    AZURE_DEPLOYMENT=${AZURE_DEPLOYMENT:-text-embedding-3-small}
    
    cat > .env << EOF
# Azure AI Foundry Configuration
AZURE_OPENAI_API_KEY=$AZURE_API_KEY
AZURE_OPENAI_ENDPOINT=$AZURE_ENDPOINT
AZURE_OPENAI_DEPLOYMENT=$AZURE_DEPLOYMENT
AZURE_OPENAI_API_VERSION=2024-02-01

# Qdrant Configuration
QDRANT_HOST=localhost
QDRANT_PORT=6337
QDRANT_COLLECTION=copilot_chats

# Database
DATABASE_PATH=./copilot_backup.db

# Search Configuration
SEARCH_LIMIT=5
SCORE_THRESHOLD=0.7
SYNC_BATCH_SIZE=10
EOF
    
    echo -e "${GREEN}✅ .env file created${NC}\n"
else
    echo -e "${GREEN}✅ .env file already exists${NC}\n"
fi

# Start Docker services
echo -e "${YELLOW}Starting Docker services...${NC}"
cd monitoring

# Check if services are already running
if docker ps | grep -q "copilot-qdrant"; then
    echo -e "${GREEN}✅ Qdrant already running${NC}"
else
    docker-compose up -d qdrant
    echo -e "${GREEN}✅ Qdrant started on port 6337${NC}"
fi

if docker ps | grep -q "copilot-prometheus"; then
    echo -e "${GREEN}✅ Prometheus already running${NC}"
else
    docker-compose up -d prometheus
    echo -e "${GREEN}✅ Prometheus started on port 9091${NC}"
fi

if docker ps | grep -q "copilot-grafana"; then
    echo -e "${GREEN}✅ Grafana already running${NC}"
else
    docker-compose up -d grafana
    echo -e "${GREEN}✅ Grafana started on port 3001${NC}"
fi

if docker ps | grep -q "copilot-metrics-exporter"; then
    echo -e "${GREEN}✅ Metrics Exporter already running${NC}"
else
    docker-compose up -d metrics-exporter
    echo -e "${GREEN}✅ Metrics Exporter started on port 8082${NC}"
fi

cd ..

# Wait for services to be healthy
echo -e "\n${YELLOW}Waiting for services to be ready...${NC}"
sleep 5

# Test Qdrant
if curl -s http://localhost:6337/health > /dev/null; then
    echo -e "${GREEN}✅ Qdrant is healthy${NC}"
else
    echo -e "${RED}❌ Qdrant is not responding${NC}"
fi

# Test Prometheus
if curl -s http://localhost:9091/-/healthy > /dev/null; then
    echo -e "${GREEN}✅ Prometheus is healthy${NC}"
else
    echo -e "${RED}❌ Prometheus is not responding${NC}"
fi

# Test Grafana
if curl -s http://localhost:3001/api/health > /dev/null; then
    echo -e "${GREEN}✅ Grafana is healthy${NC}"
else
    echo -e "${RED}❌ Grafana is not responding${NC}"
fi

# Test Metrics Exporter
if curl -s http://localhost:8082/metrics > /dev/null; then
    echo -e "${GREEN}✅ Metrics Exporter is healthy${NC}"
else
    echo -e "${RED}❌ Metrics Exporter is not responding${NC}"
fi

# Sync chats to Qdrant
echo -e "\n${YELLOW}Would you like to sync your chats to Qdrant now? (y/n)${NC}"
read -p "> " SYNC_NOW

if [ "$SYNC_NOW" = "y" ] || [ "$SYNC_NOW" = "Y" ]; then
    echo -e "${YELLOW}Syncing chats to Qdrant...${NC}"
    source .env
    python3 vectorize_chats.py --sync
    echo -e "${GREEN}✅ Sync complete${NC}"
fi

# Print summary
echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${GREEN}Services Running:${NC}"
echo -e "  🔍 Qdrant:          ${BLUE}http://localhost:6337/dashboard${NC}"
echo -e "  📊 Prometheus:      ${BLUE}http://localhost:9091${NC}"
echo -e "  📈 Grafana:         ${BLUE}http://localhost:3001${NC} (admin/copilot-admin-2024)"
echo -e "  📡 Metrics API:     ${BLUE}http://localhost:8082/metrics${NC}"

echo -e "\n${GREEN}Grafana Dashboards:${NC}"
echo -e "  • Copilot Backup Overview"
echo -e "  • Sessions Explorer"
echo -e "  • Vector Search Analytics"
echo -e "  • Workspace Explorer"

echo -e "\n${GREEN}Quick Commands:${NC}"
echo -e "  • Search chats:          ${YELLOW}python3 vectorize_chats.py --search 'your query'${NC}"
echo -e "  • Sync chats to Qdrant:  ${YELLOW}python3 vectorize_chats.py --sync${NC}"
echo -e "  • Collection info:       ${YELLOW}python3 vectorize_chats.py --info${NC}"
echo -e "  • View logs:             ${YELLOW}cd monitoring && docker-compose logs -f${NC}"
echo -e "  • Stop services:         ${YELLOW}cd monitoring && docker-compose down${NC}"

echo -e "\n${GREEN}Documentation:${NC}"
echo -e "  • Vector Search Guide:   ${BLUE}VECTOR_SEARCH_GUIDE.md${NC}"
echo -e "  • Architecture:          ${BLUE}ARCHITECTURE.md${NC}"
echo -e "  • Setup Summary:         ${BLUE}SETUP_SUMMARY.md${NC}"

echo -e "\n${YELLOW}Next Steps:${NC}"
echo -e "  1. Open Grafana: ${BLUE}http://localhost:3001${NC}"
echo -e "  2. Explore the dashboards"
echo -e "  3. Try searching: ${YELLOW}python3 vectorize_chats.py --search 'react hooks'${NC}"
echo -e "  4. Check metrics: ${BLUE}http://localhost:9091/targets${NC}"

echo ""
