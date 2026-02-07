#!/bin/bash
# Copilot Chat Backup - Monorepo Import Script
# This script safely imports the copilot-chat-backup project into a monorepo

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SOURCE_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_TARGET="tools/copilot-chat-backup"

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Copilot Chat Backup - Monorepo Import Script         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Validate prerequisites
echo -e "${YELLOW}[1/8] Checking prerequisites...${NC}"
MISSING_DEPS=0

if ! command_exists python3; then
    echo -e "${RED}✗ Python 3 is required${NC}"
    MISSING_DEPS=1
fi

if ! command_exists docker; then
    echo -e "${RED}✗ Docker is required${NC}"
    MISSING_DEPS=1
fi

if ! command_exists docker-compose || ! command_exists docker compose; then
    echo -e "${RED}✗ Docker Compose is required${NC}"
    MISSING_DEPS=1
fi

if [ $MISSING_DEPS -eq 1 ]; then
    echo -e "${RED}✗ Missing required dependencies. Please install them first.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites met${NC}"
echo ""

# Get monorepo root
echo -e "${YELLOW}[2/8] Configuring paths...${NC}"
read -p "Enter monorepo root path (absolute): " MONOREPO_ROOT

if [ -z "$MONOREPO_ROOT" ]; then
    echo -e "${RED}✗ Monorepo root path is required${NC}"
    exit 1
fi

if [ ! -d "$MONOREPO_ROOT" ]; then
    echo -e "${RED}✗ Directory does not exist: $MONOREPO_ROOT${NC}"
    exit 1
fi

# Get target path
read -p "Enter target path relative to monorepo root [$DEFAULT_TARGET]: " TARGET_REL
TARGET_REL=${TARGET_REL:-$DEFAULT_TARGET}
TARGET_PATH="$MONOREPO_ROOT/$TARGET_REL"

echo -e "${BLUE}Source: $SOURCE_PATH${NC}"
echo -e "${BLUE}Target: $TARGET_PATH${NC}"
echo ""

# Check if target exists
if [ -d "$TARGET_PATH" ]; then
    echo -e "${RED}✗ Target directory already exists: $TARGET_PATH${NC}"
    read -p "Remove existing directory? (yes/no): " REMOVE
    if [ "$REMOVE" = "yes" ]; then
        rm -rf "$TARGET_PATH"
        echo -e "${GREEN}✓ Removed existing directory${NC}"
    else
        echo -e "${RED}✗ Aborting${NC}"
        exit 1
    fi
fi

# Create target directory
echo -e "${YELLOW}[3/8] Creating target directory...${NC}"
mkdir -p "$TARGET_PATH"
echo -e "${GREEN}✓ Created: $TARGET_PATH${NC}"
echo ""

# Copy files
echo -e "${YELLOW}[4/8] Copying files...${NC}"
cp -r "$SOURCE_PATH/"* "$TARGET_PATH/" 2>/dev/null || true
cp -r "$SOURCE_PATH/".git* "$TARGET_PATH/" 2>/dev/null || true
echo -e "${GREEN}✓ Files copied${NC}"
echo ""

# Create .env file
echo -e "${YELLOW}[5/8] Creating environment configuration...${NC}"

# Check for port conflicts
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 1  # Port in use
    else
        return 0  # Port available
    fi
}

# Find available ports
PROMETHEUS_PORT=9091
GRAFANA_PORT=3001
METRICS_PORT=8082
SEARCH_PORT=8083
QDRANT_PORT=6337
REDIS_PORT=6390
NODE_EXPORTER_PORT=9101

echo "Checking port availability..."
for port in $PROMETHEUS_PORT $GRAFANA_PORT $METRICS_PORT $SEARCH_PORT $QDRANT_PORT $REDIS_PORT $NODE_EXPORTER_PORT; do
    if check_port $port; then
        echo -e "  ${GREEN}✓${NC} Port $port available"
    else
        echo -e "  ${YELLOW}⚠${NC} Port $port in use (will use environment variable override)"
    fi
done

cat > "$TARGET_PATH/.env" << EOF
# Copilot Backup - Monorepo Configuration
# Generated: $(date +%Y-%m-%d)

# Service Ports (adjust if conflicts with other services)
PROMETHEUS_PORT=$PROMETHEUS_PORT
GRAFANA_PORT=$GRAFANA_PORT
METRICS_PORT=$METRICS_PORT
SEARCH_PORT=$SEARCH_PORT
QDRANT_PORT=$QDRANT_PORT
QDRANT_GRPC_PORT=6338
REDIS_PORT=$REDIS_PORT
NODE_EXPORTER_PORT=$NODE_EXPORTER_PORT

# Grafana Admin Credentials
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=copilot-admin-2024

# Project Naming (for Docker network isolation)
COMPOSE_PROJECT_NAME=copilot-backup

# Database Location
DB_PATH=./copilot_backup.db

# Backup Configuration
GITHUB_TOKEN_FILE=./config.json
BACKUP_DIR=./backups

# Metrics Collection
METRICS_INTERVAL=300

# Log Level
LOG_LEVEL=INFO
EOF

echo -e "${GREEN}✓ Created .env file${NC}"
echo ""

# Create config template
if [ ! -f "$TARGET_PATH/config.json" ]; then
    cat > "$TARGET_PATH/config.json.example" << EOF
{
  "github_token": "YOUR_GITHUB_TOKEN_HERE",
  "github_username": "YOUR_USERNAME"
}
EOF
    echo -e "${GREEN}✓ Created config.json.example${NC}"
fi

# Update monorepo .gitignore
echo -e "${YELLOW}[6/8] Updating monorepo .gitignore...${NC}"
GITIGNORE="$MONOREPO_ROOT/.gitignore"

if [ -f "$GITIGNORE" ]; then
    # Check if already has copilot entries
    if ! grep -q "copilot-chat-backup" "$GITIGNORE"; then
        cat >> "$GITIGNORE" << EOF

# Copilot Backup Tool
$TARGET_REL/config.json
$TARGET_REL/.env
$TARGET_REL/backups/
$TARGET_REL/monitoring/grafana/data/
$TARGET_REL/monitoring/.qdrant/

# Keep database tracked
!$TARGET_REL/copilot_backup.db
EOF
        echo -e "${GREEN}✓ Updated .gitignore${NC}"
    else
        echo -e "${BLUE}ℹ .gitignore already contains copilot entries${NC}"
    fi
else
    echo -e "${YELLOW}⚠ No .gitignore found at monorepo root${NC}"
fi
echo ""

# Make scripts executable
echo -e "${YELLOW}[7/8] Setting permissions...${NC}"
chmod +x "$TARGET_PATH"/*.sh
chmod +x "$TARGET_PATH"/*.py 2>/dev/null || true
echo -e "${GREEN}✓ Scripts are executable${NC}"
echo ""

# Test installation
echo -e "${YELLOW}[8/8] Testing installation...${NC}"
cd "$TARGET_PATH"

# Test database
if python3 db_manager.py --stats >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Database script works${NC}"
else
    echo -e "${RED}✗ Database script failed${NC}"
fi

# Test monitoring status
if [ -f "start-monitoring.sh" ]; then
    ./start-monitoring.sh status >/dev/null 2>&1 || true
    echo -e "${GREEN}✓ Monitoring script works${NC}"
else
    echo -e "${YELLOW}⚠ start-monitoring.sh not found${NC}"
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✓ Import Completed Successfully!            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Project Location:${NC} $TARGET_PATH"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo -e "1. Configure GitHub token:"
echo -e "   ${BLUE}cd $TARGET_PATH${NC}"
echo -e "   ${BLUE}cp config.json.example config.json${NC}"
echo -e "   ${BLUE}nano config.json${NC}  # Add your token"
echo ""
echo -e "2. Start monitoring services:"
echo -e "   ${BLUE}./start-monitoring.sh start${NC}"
echo ""
echo -e "3. Run first backup:"
echo -e "   ${BLUE}python3 backup-copilot-chats.py${NC}"
echo ""
echo -e "4. View stats:"
echo -e "   ${BLUE}python3 db_manager.py --stats${NC}"
echo ""
echo -e "5. Access Grafana:"
echo -e "   ${BLUE}http://localhost:$GRAFANA_PORT${NC}"
echo -e "   Username: admin"
echo -e "   Password: copilot-admin-2024"
echo ""
echo -e "${YELLOW}Documentation:${NC}"
echo -e "   README.md              - Main documentation"
echo -e "   MONOREPO_INTEGRATION.md - Integration guide"
echo -e "   SETUP_SUMMARY.md       - Quick start"
echo -e "   README_DATABASE.md     - Database usage"
echo ""
echo -e "${GREEN}Happy backing up! 🚀${NC}"
