#!/bin/bash

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Setting up local Python environment for Copilot Chat Backup${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed. Please install it first.${NC}"
    exit 1
fi

echo -e "✅ Python 3 found: $(python3 --version)"

# Check/Install Pip
if ! command -v pip3 &> /dev/null; then
    echo -e "${YELLOW}⚠️  pip3 not found. Attempting to install dependencies using python3 -m pip...${NC}"
    PIP_CMD="python3 -m pip"
else
    PIP_CMD="pip3"
fi

# Create virtual environment (recommended)
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}📦 Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate
echo -e "✅ Virtual environment activated"

# Install dependencies
echo -e "${YELLOW}⬇️  Installing dependencies...${NC}"
$PIP_CMD install -r requirements-vector.txt
$PIP_CMD install -r monitoring/requirements-metrics.txt

echo -e "${GREEN}✅ Dependencies installed!${NC}"

# Check .env
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating from .env.vector.example...${NC}"
    cp .env.vector.example .env
    echo -e "${GREEN}✅ Created .env file. Please edit it with your API keys!${NC}"
else
    echo -e "✅ .env file exists"
fi

echo -e "\n${GREEN}🎉 Setup complete!${NC}"
echo -e "To start using the tools:"
echo -e "1. Activate venv: ${YELLOW}source venv/bin/activate${NC}"
echo -e "2. Sync chats:    ${YELLOW}python3 vectorize_chats.py --sync${NC}"
echo -e "3. Search:        ${YELLOW}python3 vectorize_chats.py --search 'query'${NC}"
