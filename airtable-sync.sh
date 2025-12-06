#!/bin/bash
#
# Airtable Sync for Copilot Chat Backups
# =======================================
# Wrapper script for airtable_sync.py
#
# Usage:
#   ./airtable-sync.sh setup      # Interactive setup
#   ./airtable-sync.sh sync       # Full sync
#   ./airtable-sync.sh today      # Sync today only
#   ./airtable-sync.sh status     # Check status
#   ./airtable-sync.sh install    # Add to daily cron

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/airtable_sync.py"
BACKUP_PATH="$HOME/copilot-chat-backups"
LOG_FILE="$BACKUP_PATH/logs/airtable.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════════╗"
    echo "║           Copilot Chat Backup - Airtable Integration              ║"
    echo "╚═══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_deps() {
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python 3 not found${NC}"
        exit 1
    fi
    
    # Check pyairtable
    if ! python3 -c "import pyairtable" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  pyairtable not installed${NC}"
        echo ""
        read -p "Install now? (y/n): " install
        if [[ "$install" == "y" ]]; then
            pip install pyairtable
        else
            exit 1
        fi
    fi
}

setup() {
    check_deps
    python3 "$PYTHON_SCRIPT" --setup
}

sync_all() {
    check_deps
    echo -e "${YELLOW}🔄 Running full Airtable sync...${NC}"
    python3 "$PYTHON_SCRIPT" --sync 2>&1 | tee -a "$LOG_FILE"
}

sync_today() {
    check_deps
    echo -e "${YELLOW}🔄 Syncing today's data to Airtable...${NC}"
    python3 "$PYTHON_SCRIPT" --sync-today 2>&1 | tee -a "$LOG_FILE"
}

show_status() {
    python3 "$PYTHON_SCRIPT" --status
}

install_cron() {
    echo -e "${YELLOW}📦 Adding Airtable sync to daily cron...${NC}"
    
    # Get current crontab
    current_cron=$(crontab -l 2>/dev/null || echo "")
    
    # Check if already installed
    if echo "$current_cron" | grep -q "airtable_sync.py"; then
        echo -e "${YELLOW}⚠️  Airtable sync already in crontab${NC}"
        return
    fi
    
    # Add after daily backup (11:45 PM)
    new_cron="$current_cron
# COPILOT-BACKUP: Airtable daily sync
45 23 * * * cd $SCRIPT_DIR && /usr/bin/python3 $PYTHON_SCRIPT --sync >> $LOG_FILE 2>&1"
    
    echo "$new_cron" | crontab -
    
    echo -e "${GREEN}✅ Added Airtable sync to cron (11:45 PM daily)${NC}"
}

show_help() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  setup     Interactive setup wizard (API key, Base ID)"
    echo "  sync      Run full sync to Airtable"
    echo "  today     Sync only today's sessions"
    echo "  status    Check Airtable sync status"
    echo "  install   Add daily sync to cron jobs"
    echo "  help      Show this help"
    echo ""
    echo "Setup Steps:"
    echo "  1. Create Airtable account at https://airtable.com"
    echo "  2. Create a new Base (or use existing)"
    echo "  3. Get Personal Access Token from https://airtable.com/create/tokens"
    echo "  4. Run: $0 setup"
    echo ""
    echo "Tables Created:"
    echo "  • Sessions      - All chat sessions"
    echo "  • QA_Pairs      - Extracted Q&A for training"
    echo "  • Daily_Activity - Daily summaries"
    echo "  • Projects      - Project statistics"
}

# Main
print_header

case "${1:-help}" in
    setup)
        setup
        ;;
    sync)
        sync_all
        ;;
    today)
        sync_today
        ;;
    status)
        show_status
        ;;
    install)
        install_cron
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}\n"
        show_help
        exit 1
        ;;
esac
