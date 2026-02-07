# 📊 Local Database Storage

## Overview

The copilot chat backup now includes a **local SQLite database** (`copilot_backup.db`) stored directly in the repository. This allows you to:

- 📈 Track backup history over time
- 🔍 Query historical metrics locally
- 📊 Analyze trends without external services
- 💾 Keep all data portable with the repo

## Database Schema

### Tables

1. **backup_runs** - Stores each backup execution

   - timestamp, total_sessions, total_messages, total_size_bytes, total_workspaces

2. **sessions** - Individual chat sessions

   - session_id, project, message_count, user/assistant messages, duration

3. **workspaces** - Workspace-level aggregations

   - workspace_name, session_count, total_messages, active_days

4. **hourly_activity** - Message distribution by hour
5. **daily_activity** - Message distribution by date

## Usage

### View Statistics

```bash
python db_manager.py --stats
```

### Top Workspaces

```bash
python db_manager.py --top-workspaces 10
```

### Workspace History

```bash
python db_manager.py --workspace howaiconnects
```

### Activity Trend

```bash
python db_manager.py --trend 30
```

### Export to JSON

```bash
python db_manager.py --export backup_data.json
```

## Automatic Updates

The database is automatically updated:

- ✅ Every time the metrics exporter scans backups
- ✅ On startup of the monitoring stack
- ✅ When backup scripts complete

## Database Location

**File:** `/home/adham/Dev/copilot-chat-backup/copilot_backup.db`

The database file is **tracked in git** to ensure:

- Historical data travels with the repo
- No external dependencies needed
- Easy backup and restore
- Portable across machines

## Integration

### Metrics Exporter

The metrics exporter (`monitoring/backup_metrics.py`) automatically saves data to the database on each scan.

### Grafana

You can create additional Grafana dashboards that query the SQLite database using the SQLite datasource plugin.

### Custom Scripts

Use the `BackupDatabase` class in your own scripts:

```python
from db_manager import BackupDatabase

db = BackupDatabase('copilot_backup.db')
stats = db.get_stats_summary()
workspaces = db.get_top_workspaces(10)
db.close()
```

## Maintenance

### Database Size

The database grows with each backup run. Monitor size with:

```bash
ls -lh copilot_backup.db
```

### Cleanup Old Data

```python
# Connect to database and manually delete old runs if needed
sqlite3 copilot_backup.db
DELETE FROM backup_runs WHERE timestamp < '2025-01-01';
VACUUM;
```

### Backup Database

```bash
# Create a backup copy
cp copilot_backup.db copilot_backup.db.backup

# Or export to JSON
python db_manager.py --export backup_$(date +%Y%m%d).json
```

## Benefits

✅ **Portable** - Everything in one repo  
✅ **Queryable** - SQL queries for analysis  
✅ **Historical** - Track changes over time  
✅ **Lightweight** - SQLite requires no server  
✅ **Git-friendly** - Track changes in version control  
✅ **Zero-config** - Works out of the box

## Queries

### Growth Over Time

```sql
SELECT date, total_messages
FROM backup_runs
ORDER BY timestamp;
```

### Most Active Workspaces

```sql
SELECT workspace_name, SUM(total_messages) as total
FROM workspaces
GROUP BY workspace_name
ORDER BY total DESC
LIMIT 10;
```

### Activity by Day of Week

```sql
SELECT strftime('%w', date) as day_of_week, SUM(message_count) as total
FROM daily_activity
GROUP BY day_of_week;
```
