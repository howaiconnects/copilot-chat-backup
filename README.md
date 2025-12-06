# Copilot Chat Backup

🔄 A comprehensive backup and analysis system for GitHub Copilot chat sessions in VS Code.

Works with **any repository** - local or remote. Keep your AI conversations organized, searchable, and ready for analysis.

## Features

- 🔄 **Automatic Backup**: Hourly/daily backups of all chat sessions
- 📁 **Project Organization**: Chats organized by workspace/project  
- 📅 **Daily Summaries**: Activity reports by date (Markdown)
- 🤖 **AI-Friendly Export**: JSONL and Q&A pair formats for RAG/training
- �� **Full-Text Search**: Query across all conversations
- 📊 **Statistics**: Usage analytics and topic extraction
- ☁️ **Airtable Sync**: Optional sync to Airtable for browsing/filtering
- 🔀 **GitHub Sync**: Push backups to an orphan branch

## Quick Start

```bash
# Clone the repo
git clone https://github.com/yourusername/copilot-chat-backup.git
cd copilot-chat-backup

# Make scripts executable
chmod +x *.sh *.py

# Run first backup
./backup-copilot-chats.sh

# Or use the enhanced backup script
python3 backup-all-chats.py

# Setup automatic backups (hourly + daily + weekly)
./setup-cron-backups.sh install

# Check status
./setup-cron-backups.sh status
```

## Installation

### Option 1: Clone to a central location
```bash
# Recommended: Keep in a central tools directory
git clone https://github.com/yourusername/copilot-chat-backup.git ~/tools/copilot-chat-backup

# Add to PATH (optional)
echo 'export PATH="$HOME/tools/copilot-chat-backup:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Option 2: Install globally with symlinks
```bash
git clone https://github.com/yourusername/copilot-chat-backup.git ~/tools/copilot-chat-backup
sudo ln -s ~/tools/copilot-chat-backup/backup-copilot-chats.sh /usr/local/bin/copilot-backup
```

## Backup Location

Default: `~/copilot-chat-backups/`

```
copilot-chat-backups/
├── raw/                    # Original JSON files by project
│   ├── my-project/
│   └── another-repo/
├── markdown/               # Human-readable conversations
│   └── my-project/
│       └── 2025-12-05_session_abc123.md
├── daily/                  # Daily activity summaries
│   └── 2025-12-05.md
├── hourly/                 # Hourly incremental summaries
├── ai-export/              # AI-friendly formats
│   ├── latest_export.json  # Full structured export
│   ├── sessions.jsonl      # One session per line
│   └── qa_pairs.jsonl      # Q&A pairs for RAG/training
├── index/                  # Search indexes
│   └── master_index.json
├── backup_tracking.db      # SQLite tracking database
└── logs/                   # Backup logs
```

## Commands Reference

### Backup

```bash
# Full backup of all workspaces
python3 backup-all-chats.py

# Incremental backup (only new/changed)
python3 backup-all-chats.py --incremental

# Manual schedule type
python3 backup-all-chats.py --schedule daily

# Legacy bash script
./backup-copilot-chats.sh
./backup-copilot-chats.sh --workspace my-project
./backup-copilot-chats.sh --list
```

### Search

```bash
# Search all conversations
python3 search-chats.py "error handling"

# Search in specific project
python3 search-chats.py "authentication" --project my-repo

# Search last 7 days
python3 search-chats.py "API" --days 7

# Show today's conversations
python3 search-chats.py --today

# Show statistics
python3 search-chats.py --stats
```

### Cron Management

```bash
# Install all cron jobs (hourly + daily + weekly)
./setup-cron-backups.sh install

# Check status
./setup-cron-backups.sh status

# Remove cron jobs
./setup-cron-backups.sh remove

# Run test backup
./setup-cron-backups.sh test
```

### Airtable Integration (Optional)

```bash
# Interactive setup
./airtable-sync.sh setup

# Sync all data
./airtable-sync.sh sync

# Sync today only
./airtable-sync.sh today

# Add to cron
./airtable-sync.sh install
```

### GitHub Sync (Optional)

```bash
# Initialize backup branch
./sync-to-github.sh --init

# Sync backups to GitHub
./sync-to-github.sh

# Check status
./sync-to-github.sh --status
```

## AI Export Formats

### Q&A Pairs (`qa_pairs.jsonl`)

Perfect for RAG systems and fine-tuning:

```jsonl
{"project": "my-repo", "date": "2025-12-05", "question": "How do I...", "answer": "You can..."}
{"project": "my-repo", "date": "2025-12-05", "question": "What is...", "answer": "It is..."}
```

### Sessions JSONL (`sessions.jsonl`)

One complete session per line:

```jsonl
{"id": "abc12345", "project": "my-repo", "messages": 24, "conversation": [...]}
```

### Full Export (`latest_export.json`)

Complete export with all metadata for complex analysis.

## Integration Examples

### RAG System
```python
import json

with open('~/copilot-chat-backups/ai-export/qa_pairs.jsonl') as f:
    for line in f:
        qa = json.loads(line)
        # Index in your vector database
        embed_and_store(qa['question'], qa['answer'])
```

### Fine-tuning Data
```python
with open('qa_pairs.jsonl') as f:
    training_data = [
        {"instruction": json.loads(line)['question'], 
         "output": json.loads(line)['answer']}
        for line in f
    ]
```

## VS Code Chat Locations

Auto-discovered from:
- **Linux**: `~/.config/Code/User/workspaceStorage/*/state.vscdb`
- **macOS**: `~/Library/Application Support/Code/User/workspaceStorage/*/state.vscdb`
- **Windows**: `%APPDATA%/Code/User/workspaceStorage/*/state.vscdb`

## Configuration

Edit `config.json` to customize:
- Tracked project paths
- Backup retention period
- Export format options
- Sensitive data filters

## Requirements

- Python 3.7+
- No external dependencies (uses stdlib only)
- Optional: `pyairtable` for Airtable integration

## License

MIT License - Use freely in any project!
