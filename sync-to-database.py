#!/usr/bin/env python3
"""
Sync metrics from the API to the local SQLite database.
Run this to populate the database with current metrics.
"""

import sys
import json
from urllib.request import urlopen
from urllib.error import URLError
from datetime import datetime
from db_manager import BackupDatabase

def fetch_metrics(api_url="http://localhost:8082/api/metrics"):
    """Fetch metrics from the API."""
    try:
        with urlopen(api_url, timeout=10) as response:
            return json.loads(response.read().decode())
    except (URLError, Exception) as e:
        print(f"❌ Error fetching metrics: {e}")
        sys.exit(1)

def main():
    print("🔄 Syncing metrics to database...")
    
    # Fetch current metrics
    metrics = fetch_metrics()
    
    # Save to database
    db = BackupDatabase('copilot_backup.db')
    try:
        backup_run_id = db.save_backup_run(metrics)
        
        # Get stats
        stats = db.get_stats_summary()
        
        print(f"✅ Saved backup run #{backup_run_id}")
        print(f"\n📊 Database Summary:")
        print(f"   Total Backups: {stats['total_backups']}")
        print(f"   Unique Sessions: {stats['unique_sessions']}")
        
        if stats['latest_backup']:
            latest = stats['latest_backup']
            print(f"\n   Latest Backup:")
            print(f"     Timestamp: {latest['timestamp']}")
            print(f"     Sessions: {latest['total_sessions']}")
            print(f"     Messages: {latest['total_messages']}")
            print(f"     Workspaces: {latest['total_workspaces']}")
            print(f"     Size: {latest['total_size_bytes'] / 1024 / 1024 / 1024:.2f} GB")
    
    finally:
        db.close()
    
    print("\n✨ Sync complete!")

if __name__ == '__main__':
    main()
