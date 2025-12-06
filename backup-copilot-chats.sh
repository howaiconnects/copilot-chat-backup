#!/bin/bash
#
# GitHub Copilot Chat Backup Script
# ==================================
# Wrapper script for the Python backup system
#
# Usage:
#   ./backup-copilot-chats.sh                    # Full backup
#   ./backup-copilot-chats.sh --workspace hub    # Specific workspace
#   ./backup-copilot-chats.sh --list             # List workspaces
#   ./backup-copilot-chats.sh --cron-setup       # Setup daily cron job

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/backup-copilot-chats.py"
DEFAULT_BACKUP_PATH="$HOME/copilot-chat-backups"
LOG_FILE="$DEFAULT_BACKUP_PATH/backup.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║       GitHub Copilot Chat Backup System                   ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --list, -l              List all discovered workspaces"
    echo "  --workspace, -w NAME    Backup only specific workspace"
    echo "  --output, -o PATH       Custom backup destination"
    echo "  --cron-setup            Setup daily automatic backup"
    echo "  --cron-remove           Remove automatic backup"
    echo "  --status                Show backup status and stats"
    echo "  --help, -h              Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                      # Full backup of all workspaces"
    echo "  $0 -w aiconnects-hub    # Backup only aiconnects-hub"
    echo "  $0 --cron-setup         # Setup daily backup at 11 PM"
}

setup_cron() {
    echo -e "${YELLOW}Setting up daily backup cron job...${NC}"
    
    # Create cron entry (runs daily at 11 PM)
    CRON_CMD="0 23 * * * cd $SCRIPT_DIR && python3 $PYTHON_SCRIPT >> $LOG_FILE 2>&1"
    
    # Check if already exists
    if crontab -l 2>/dev/null | grep -q "backup-copilot-chats.py"; then
        echo -e "${YELLOW}Cron job already exists. Updating...${NC}"
        crontab -l 2>/dev/null | grep -v "backup-copilot-chats.py" | crontab -
    fi
    
    # Add new cron job
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    
    echo -e "${GREEN}✅ Cron job installed!${NC}"
    echo "   Schedule: Daily at 11:00 PM"
    echo "   Command: python3 $PYTHON_SCRIPT"
    echo "   Log: $LOG_FILE"
    echo ""
    echo "Current cron jobs:"
    crontab -l | grep -E "(copilot|backup)" || echo "  (none found)"
}

remove_cron() {
    echo -e "${YELLOW}Removing backup cron job...${NC}"
    
    if crontab -l 2>/dev/null | grep -q "backup-copilot-chats.py"; then
        crontab -l 2>/dev/null | grep -v "backup-copilot-chats.py" | crontab -
        echo -e "${GREEN}✅ Cron job removed${NC}"
    else
        echo -e "${YELLOW}No cron job found${NC}"
    fi
}

show_status() {
    echo -e "${BLUE}Backup Status${NC}"
    echo "============="
    echo ""
    
    if [ -d "$DEFAULT_BACKUP_PATH" ]; then
        echo -e "${GREEN}✅ Backup directory exists${NC}: $DEFAULT_BACKUP_PATH"
        echo ""
        
        # Show directory sizes
        echo "Directory sizes:"
        du -sh "$DEFAULT_BACKUP_PATH"/* 2>/dev/null | while read size dir; do
            echo "  $size  $(basename "$dir")"
        done
        echo ""
        
        # Show latest backup info
        if [ -f "$DEFAULT_BACKUP_PATH/index/master_index.json" ]; then
            echo "Latest backup stats:"
            cat "$DEFAULT_BACKUP_PATH/index/master_index.json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f\"  Generated: {data.get('generated', 'N/A')}\")
stats = data.get('stats', {})
print(f\"  Sessions: {stats.get('total_sessions', 0)}\")
print(f\"  Messages: {stats.get('total_messages', 0)}\")
print(f\"  Size: {stats.get('total_size_bytes', 0) / (1024*1024):.2f} MB\")
"
        fi
        
        # Show recent daily summaries
        echo ""
        echo "Recent daily summaries:"
        ls -t "$DEFAULT_BACKUP_PATH/daily/"*.md 2>/dev/null | head -5 | while read f; do
            echo "  $(basename "$f")"
        done
        
    else
        echo -e "${YELLOW}⚠️ No backup directory found${NC}"
        echo "Run '$0' to create first backup"
    fi
    
    echo ""
    echo "Cron job status:"
    if crontab -l 2>/dev/null | grep -q "backup-copilot-chats.py"; then
        crontab -l 2>/dev/null | grep "backup-copilot-chats.py"
    else
        echo "  No automatic backup scheduled"
    fi
}

# Main execution
print_header

case "$1" in
    --cron-setup)
        setup_cron
        ;;
    --cron-remove)
        remove_cron
        ;;
    --status)
        show_status
        ;;
    --help|-h)
        print_usage
        ;;
    --list|-l)
        python3 "$PYTHON_SCRIPT" --list-workspaces
        ;;
    *)
        # Ensure backup directory exists
        mkdir -p "$DEFAULT_BACKUP_PATH"
        
        # Run Python backup script with all arguments
        echo -e "${YELLOW}Starting backup...${NC}"
        echo ""
        python3 "$PYTHON_SCRIPT" "$@"
        
        echo ""
        echo -e "${GREEN}Backup location: $DEFAULT_BACKUP_PATH${NC}"
        echo ""
        echo "Useful commands:"
        echo "  View daily summary:  cat $DEFAULT_BACKUP_PATH/daily/$(date +%Y-%m-%d).md"
        echo "  View AI export:      cat $DEFAULT_BACKUP_PATH/ai-export/qa_pairs.json | jq '.[:5]'"
        echo "  Setup auto backup:   $0 --cron-setup"
        ;;
esac
