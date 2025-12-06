#!/bin/bash
#
# GitHub Copilot Chat Backup - Cron Setup Script
# ================================================
# Sets up multiple daily backups to capture all chat activity
#
# Schedules:
#   - Hourly incremental (9 AM - 11 PM, every 2 hours)
#   - Daily full backup (11:30 PM)
#   - Weekly archive (Sunday 2 AM)
#
# Usage:
#   ./setup-cron-backups.sh install     # Install all cron jobs
#   ./setup-cron-backups.sh remove      # Remove all cron jobs
#   ./setup-cron-backups.sh status      # Check current status
#   ./setup-cron-backups.sh test        # Run test backup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup-all-chats.py"
BACKUP_PATH="$HOME/copilot-chat-backups"
LOG_DIR="$BACKUP_PATH/logs"
PYTHON_PATH="/usr/bin/python3"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════════╗"
    echo "║       GitHub Copilot Chat Backup - Multi-Schedule Cron Setup      ║"
    echo "╚═══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Ensure directories exist
mkdir -p "$LOG_DIR"

# Cron job definitions
# Format: "schedule|description|command"
CRON_JOBS=(
    # Hourly incremental backups during work hours (every 2 hours, 9 AM - 11 PM)
    "0 9,11,13,15,17,19,21,23 * * *|Hourly incremental backup|cd $SCRIPT_DIR && $PYTHON_PATH $BACKUP_SCRIPT --schedule hourly --incremental >> $LOG_DIR/hourly.log 2>&1"
    
    # Daily full backup at 11:30 PM
    "30 23 * * *|Daily full backup|cd $SCRIPT_DIR && $PYTHON_PATH $BACKUP_SCRIPT --schedule daily >> $LOG_DIR/daily.log 2>&1"
    
    # Weekly archive on Sunday at 2 AM
    "0 2 * * 0|Weekly archive|cd $SCRIPT_DIR && $PYTHON_PATH $BACKUP_SCRIPT --schedule weekly >> $LOG_DIR/weekly.log 2>&1 && find $BACKUP_PATH/ai-export -name 'export_*.json' -mtime +30 -delete"
)

install_cron() {
    echo -e "${YELLOW}📦 Installing cron jobs...${NC}\n"
    
    # Get current crontab (or empty if none)
    current_cron=$(crontab -l 2>/dev/null || echo "")
    
    # Remove existing copilot backup jobs
    new_cron=$(echo "$current_cron" | grep -v "backup-all-chats.py" | grep -v "# COPILOT-BACKUP" || true)
    
    # Add header
    new_cron="$new_cron
# ============================================================================
# COPILOT-BACKUP: GitHub Copilot Chat Backup Jobs
# Installed: $(date -Iseconds)
# ============================================================================"
    
    # Add each job
    for job in "${CRON_JOBS[@]}"; do
        IFS='|' read -r schedule desc command <<< "$job"
        new_cron="$new_cron
# COPILOT-BACKUP: $desc
$schedule $command"
        echo -e "  ${GREEN}✓${NC} $desc"
        echo -e "    Schedule: ${BLUE}$schedule${NC}"
    done
    
    # Install new crontab
    echo "$new_cron" | crontab -
    
    echo -e "\n${GREEN}✅ Cron jobs installed successfully!${NC}\n"
    echo "Schedule overview:"
    echo "  • Hourly: 9 AM, 11 AM, 1 PM, 3 PM, 5 PM, 7 PM, 9 PM, 11 PM (incremental)"
    echo "  • Daily: 11:30 PM (full backup)"
    echo "  • Weekly: Sunday 2 AM (archive + cleanup)"
    echo ""
    echo "Logs: $LOG_DIR/"
    echo "Backups: $BACKUP_PATH/"
}

remove_cron() {
    echo -e "${YELLOW}🗑️ Removing cron jobs...${NC}\n"
    
    current_cron=$(crontab -l 2>/dev/null || echo "")
    
    # Remove copilot backup jobs and comments
    new_cron=$(echo "$current_cron" | grep -v "backup-all-chats.py" | grep -v "COPILOT-BACKUP" | grep -v "^#.*Copilot" || true)
    
    # Clean up empty lines
    new_cron=$(echo "$new_cron" | cat -s)
    
    if [ -z "$new_cron" ]; then
        crontab -r 2>/dev/null || true
    else
        echo "$new_cron" | crontab -
    fi
    
    echo -e "${GREEN}✅ All Copilot backup cron jobs removed${NC}"
}

show_status() {
    echo -e "${BLUE}📊 Copilot Backup Status${NC}\n"
    
    # Check if cron jobs are installed
    echo "Cron Jobs:"
    if crontab -l 2>/dev/null | grep -q "backup-all-chats.py"; then
        crontab -l 2>/dev/null | grep -E "(COPILOT-BACKUP|backup-all-chats)" | while read line; do
            if [[ "$line" == "#"* ]]; then
                echo -e "  ${CYAN}$line${NC}"
            else
                echo -e "  ${GREEN}✓${NC} $line"
            fi
        done
    else
        echo -e "  ${RED}✗ No cron jobs installed${NC}"
    fi
    
    echo ""
    
    # Check backup directory
    echo "Backup Directory: $BACKUP_PATH"
    if [ -d "$BACKUP_PATH" ]; then
        echo -e "  ${GREEN}✓${NC} Exists"
        
        # Show sizes
        echo ""
        echo "Directory sizes:"
        du -sh "$BACKUP_PATH"/* 2>/dev/null | while read size dir; do
            echo "  $(basename "$dir"): $size"
        done
        
        # Show latest backups
        echo ""
        echo "Recent activity:"
        
        if [ -d "$BACKUP_PATH/daily" ]; then
            latest_daily=$(ls -t "$BACKUP_PATH/daily/"*.md 2>/dev/null | head -1)
            if [ -n "$latest_daily" ]; then
                echo "  Latest daily: $(basename "$latest_daily")"
            fi
        fi
        
        if [ -d "$BACKUP_PATH/hourly" ]; then
            latest_hourly=$(ls -t "$BACKUP_PATH/hourly/"*.md 2>/dev/null | head -1)
            if [ -n "$latest_hourly" ]; then
                echo "  Latest hourly: $(basename "$latest_hourly")"
            fi
        fi
        
        # Show database stats
        if [ -f "$BACKUP_PATH/backup_tracking.db" ]; then
            echo ""
            echo "Database stats:"
            sqlite3 "$BACKUP_PATH/backup_tracking.db" "SELECT '  Total sessions tracked: ' || COUNT(*) FROM sessions;" 2>/dev/null || echo "  (unable to read sessions)"
            sqlite3 "$BACKUP_PATH/backup_tracking.db" "SELECT '  Unique projects: ' || COUNT(DISTINCT project_name) FROM sessions;" 2>/dev/null || echo "  (unable to read projects)"
            sqlite3 "$BACKUP_PATH/backup_tracking.db" "SELECT '  Last backup: ' || MAX(timestamp) FROM backups;" 2>/dev/null || echo "  (unable to read backups)"
        fi
    else
        echo -e "  ${YELLOW}⚠ Not created yet${NC}"
    fi
    
    echo ""
    
    # Check logs
    echo "Recent logs:"
    if [ -d "$LOG_DIR" ]; then
        for log in "$LOG_DIR"/*.log; do
            if [ -f "$log" ]; then
                name=$(basename "$log")
                lines=$(wc -l < "$log" 2>/dev/null || echo 0)
                last_entry=$(tail -1 "$log" 2>/dev/null | head -c 60)
                echo "  $name: $lines lines"
                if [ -n "$last_entry" ]; then
                    echo "    Last: $last_entry..."
                fi
            fi
        done
    else
        echo "  No logs yet"
    fi
}

run_test() {
    echo -e "${YELLOW}🧪 Running test backup...${NC}\n"
    
    # Run a quick backup
    cd "$SCRIPT_DIR"
    $PYTHON_PATH "$BACKUP_SCRIPT" --schedule manual --incremental
    
    echo -e "\n${GREEN}✅ Test backup complete${NC}"
}

show_help() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  install   Install all cron jobs for automated backups"
    echo "  remove    Remove all cron jobs"
    echo "  status    Show current status and statistics"
    echo "  test      Run a test backup now"
    echo "  help      Show this help"
    echo ""
    echo "Backup Schedule:"
    echo "  • Every 2 hours (9 AM - 11 PM): Incremental backup of new/changed chats"
    echo "  • Daily at 11:30 PM: Full backup of all sessions"
    echo "  • Sunday 2 AM: Weekly archive with old file cleanup"
    echo ""
    echo "Backup Location: $BACKUP_PATH"
    echo ""
    echo "Examples:"
    echo "  $0 install    # Setup automatic backups"
    echo "  $0 status     # Check if everything is working"
    echo "  $0 test       # Run backup manually"
}

# Main
print_header

case "${1:-help}" in
    install)
        install_cron
        ;;
    remove)
        remove_cron
        ;;
    status)
        show_status
        ;;
    test)
        run_test
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
