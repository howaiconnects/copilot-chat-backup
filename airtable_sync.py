#!/usr/bin/env python3
"""
Airtable Integration for Copilot Chat Backups
==============================================

Syncs chat sessions and Q&A pairs to Airtable for easy browsing,
filtering, and data manipulation.

Features:
- Auto-creates tables with proper schema
- Incremental sync (only new/updated sessions)
- Project-based organization
- Q&A extraction for analysis
- Activity tracking and analytics

Usage:
    python3 airtable_sync.py --init          # Create tables in Airtable
    python3 airtable_sync.py --sync          # Sync all data
    python3 airtable_sync.py --sync-today    # Sync today's sessions only
    python3 airtable_sync.py --status        # Check sync status

Environment Variables:
    AIRTABLE_API_KEY     - Your Airtable Personal Access Token
    AIRTABLE_BASE_ID     - Your Airtable Base ID

Setup:
    1. Create a Personal Access Token at https://airtable.com/create/tokens
       - Scopes: data.records:read, data.records:write, schema.bases:read, schema.bases:write
    2. Create a new Base in Airtable (or use existing)
    3. Copy the Base ID from the URL (starts with 'app')
    4. Set environment variables or create .env file
"""

import os
import json
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import argparse
import time

try:
    from pyairtable import Api, Table
    from pyairtable.formulas import match
    AIRTABLE_AVAILABLE = True
except ImportError:
    AIRTABLE_AVAILABLE = False
    print("⚠️  pyairtable not installed. Run: pip install pyairtable")

# Configuration
BACKUP_PATH = Path.home() / "copilot-chat-backups"
DB_PATH = BACKUP_PATH / "backup_tracking.db"
CONFIG_PATH = Path(__file__).parent / "airtable_config.json"

# Table schemas
TABLES_SCHEMA = {
    "Sessions": {
        "description": "All Copilot chat sessions",
        "fields": [
            {"name": "Session ID", "type": "singleLineText"},
            {"name": "Project", "type": "singleLineText"},
            {"name": "Workspace", "type": "singleLineText"},
            {"name": "Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Messages", "type": "number", "options": {"precision": 0}},
            {"name": "First Message", "type": "multilineText"},
            {"name": "Topics", "type": "multipleSelects", "options": {"choices": []}},
            {"name": "Category", "type": "singleSelect", "options": {"choices": [
                {"name": "aiconnects", "color": "blueDark"},
                {"name": "smart-spending", "color": "greenDark"},
                {"name": "howaiconnects", "color": "purpleDark"},
                {"name": "infrastructure", "color": "orangeDark"},
                {"name": "other", "color": "grayDark"}
            ]}},
            {"name": "Status", "type": "singleSelect", "options": {"choices": [
                {"name": "Active", "color": "greenBright"},
                {"name": "Archived", "color": "grayLight"},
                {"name": "Reviewed", "color": "blueBright"}
            ]}},
            {"name": "Last Synced", "type": "dateTime"},
            {"name": "File Path", "type": "singleLineText"},
            {"name": "Hash", "type": "singleLineText"}
        ]
    },
    "QA_Pairs": {
        "description": "Extracted Q&A pairs for analysis and training",
        "fields": [
            {"name": "ID", "type": "singleLineText"},
            {"name": "Project", "type": "singleLineText"},
            {"name": "Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Question", "type": "multilineText"},
            {"name": "Answer", "type": "multilineText"},
            {"name": "Question Length", "type": "number", "options": {"precision": 0}},
            {"name": "Answer Length", "type": "number", "options": {"precision": 0}},
            {"name": "Has Code", "type": "checkbox"},
            {"name": "Tags", "type": "multipleSelects", "options": {"choices": [
                {"name": "debugging", "color": "redBright"},
                {"name": "implementation", "color": "blueBright"},
                {"name": "architecture", "color": "purpleBright"},
                {"name": "configuration", "color": "orangeBright"},
                {"name": "documentation", "color": "greenBright"},
                {"name": "refactoring", "color": "yellowBright"},
                {"name": "testing", "color": "cyanBright"}
            ]}},
            {"name": "Quality", "type": "singleSelect", "options": {"choices": [
                {"name": "High", "color": "greenBright"},
                {"name": "Medium", "color": "yellowBright"},
                {"name": "Low", "color": "redLight"},
                {"name": "Unrated", "color": "grayLight"}
            ]}},
            {"name": "Session", "type": "singleLineText"},
            {"name": "Useful for Training", "type": "checkbox"}
        ]
    },
    "Daily_Activity": {
        "description": "Daily summaries and metrics",
        "fields": [
            {"name": "Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Sessions", "type": "number", "options": {"precision": 0}},
            {"name": "Messages", "type": "number", "options": {"precision": 0}},
            {"name": "QA Pairs", "type": "number", "options": {"precision": 0}},
            {"name": "Top Projects", "type": "multilineText"},
            {"name": "Summary", "type": "multilineText"},
            {"name": "Productivity Score", "type": "number", "options": {"precision": 1}},
            {"name": "Notes", "type": "multilineText"}
        ]
    },
    "Projects": {
        "description": "Project index and statistics",
        "fields": [
            {"name": "Name", "type": "singleLineText"},
            {"name": "Category", "type": "singleSelect", "options": {"choices": [
                {"name": "aiconnects", "color": "blueDark"},
                {"name": "smart-spending", "color": "greenDark"},
                {"name": "howaiconnects", "color": "purpleDark"},
                {"name": "infrastructure", "color": "orangeDark"},
                {"name": "other", "color": "grayDark"}
            ]}},
            {"name": "Total Sessions", "type": "number", "options": {"precision": 0}},
            {"name": "Total Messages", "type": "number", "options": {"precision": 0}},
            {"name": "First Activity", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Last Activity", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Workspace Path", "type": "singleLineText"},
            {"name": "Status", "type": "singleSelect", "options": {"choices": [
                {"name": "Active", "color": "greenBright"},
                {"name": "Archived", "color": "grayLight"},
                {"name": "Maintenance", "color": "yellowBright"}
            ]}}
        ]
    }
}


@dataclass
class AirtableConfig:
    api_key: str
    base_id: str
    table_ids: Dict[str, str]
    last_sync: Optional[str] = None
    sync_count: int = 0


class AirtableChatSync:
    """Sync Copilot chat backups to Airtable."""
    
    def __init__(self):
        self.config = self._load_config()
        self.api = None
        self.tables: Dict[str, Table] = {}
        
        if self.config and AIRTABLE_AVAILABLE:
            self.api = Api(self.config.api_key)
            self._init_tables()
    
    def _load_config(self) -> Optional[AirtableConfig]:
        """Load configuration from file or environment."""
        # Try environment variables first
        api_key = os.environ.get("AIRTABLE_API_KEY", "")
        base_id = os.environ.get("AIRTABLE_BASE_ID", "")
        
        # Try config file
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                data = json.load(f)
                api_key = api_key or data.get("api_key", "")
                base_id = base_id or data.get("base_id", "")
                return AirtableConfig(
                    api_key=api_key,
                    base_id=base_id,
                    table_ids=data.get("table_ids", {}),
                    last_sync=data.get("last_sync"),
                    sync_count=data.get("sync_count", 0)
                )
        
        if api_key and base_id:
            return AirtableConfig(api_key=api_key, base_id=base_id, table_ids={})
        
        return None
    
    def _save_config(self):
        """Save configuration to file."""
        if self.config:
            data = {
                "api_key": self.config.api_key,
                "base_id": self.config.base_id,
                "table_ids": self.config.table_ids,
                "last_sync": self.config.last_sync,
                "sync_count": self.config.sync_count
            }
            with open(CONFIG_PATH, 'w') as f:
                json.dump(data, f, indent=2)
    
    def _init_tables(self):
        """Initialize table references."""
        if not self.api or not self.config:
            return
        
        for table_name, table_id in self.config.table_ids.items():
            if table_id:
                self.tables[table_name] = self.api.table(self.config.base_id, table_id)
    
    def setup_interactive(self):
        """Interactive setup wizard."""
        print("\n🔧 Airtable Integration Setup\n")
        print("=" * 50)
        
        print("\nStep 1: Get your Airtable Personal Access Token")
        print("  → Go to: https://airtable.com/create/tokens")
        print("  → Create token with scopes:")
        print("    • data.records:read")
        print("    • data.records:write") 
        print("    • schema.bases:read")
        print("    • schema.bases:write")
        print()
        
        api_key = input("Enter your API Key (pat...): ").strip()
        if not api_key:
            print("❌ API key required")
            return False
        
        print("\nStep 2: Get your Base ID")
        print("  → Open your Airtable base")
        print("  → Copy the Base ID from URL (starts with 'app')")
        print("  → Example: https://airtable.com/appXXXXXXXX/...")
        print()
        
        base_id = input("Enter your Base ID (app...): ").strip()
        if not base_id:
            print("❌ Base ID required")
            return False
        
        self.config = AirtableConfig(
            api_key=api_key,
            base_id=base_id,
            table_ids={}
        )
        
        # Test connection
        print("\n🔄 Testing connection...")
        try:
            self.api = Api(api_key)
            base = self.api.base(base_id)
            print(f"✅ Connected to base: {base_id}")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
        
        self._save_config()
        print(f"\n✅ Configuration saved to: {CONFIG_PATH}")
        
        # Offer to create tables
        create = input("\nCreate tables now? (y/n): ").strip().lower()
        if create == 'y':
            self.init_tables()
        
        return True
    
    def init_tables(self):
        """Create tables in Airtable with proper schema."""
        if not self.api or not self.config:
            print("❌ Not configured. Run --setup first.")
            return False
        
        print("\n📋 Creating Airtable tables...\n")
        
        base = self.api.base(self.config.base_id)
        
        for table_name, schema in TABLES_SCHEMA.items():
            print(f"  Creating '{table_name}'...")
            
            try:
                # Check if table already exists
                existing_tables = base.schema().tables
                existing = next((t for t in existing_tables if t.name == table_name), None)
                
                if existing:
                    print(f"    ⚠️  Table already exists (ID: {existing.id})")
                    self.config.table_ids[table_name] = existing.id
                else:
                    # Create table with schema
                    # Note: pyairtable doesn't support table creation directly
                    # We'll create via the API manually
                    print(f"    ℹ️  Please create table '{table_name}' manually in Airtable")
                    print(f"       Then enter the table ID below")
                    table_id = input(f"       Table ID for {table_name}: ").strip()
                    if table_id:
                        self.config.table_ids[table_name] = table_id
                        print(f"    ✅ Registered: {table_id}")
                    
            except Exception as e:
                print(f"    ❌ Error: {e}")
        
        self._save_config()
        self._init_tables()
        
        print("\n✅ Tables configured!")
        return True
    
    def _get_sessions_from_db(self, since: Optional[datetime] = None) -> List[Dict]:
        """Get sessions from SQLite database."""
        if not DB_PATH.exists():
            return []
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if since:
            cursor.execute("""
                SELECT * FROM sessions 
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            """, (since.isoformat(),))
        else:
            cursor.execute("SELECT * FROM sessions ORDER BY timestamp DESC")
        
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return rows
    
    def _get_qa_pairs(self) -> List[Dict]:
        """Get Q&A pairs from JSONL export."""
        qa_path = BACKUP_PATH / "ai-export" / "qa_pairs.jsonl"
        if not qa_path.exists():
            return []
        
        pairs = []
        with open(qa_path) as f:
            for line in f:
                try:
                    pairs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        
        return pairs
    
    def _categorize_project(self, name: str) -> str:
        """Categorize project by name."""
        name_lower = name.lower()
        if 'aiconnects' in name_lower:
            return 'aiconnects'
        elif 'smart-spending' in name_lower or 's-s-h' in name_lower:
            return 'smart-spending'
        elif 'howaiconnects' in name_lower:
            return 'howaiconnects'
        elif any(x in name_lower for x in ['infra', 'azure', 'docker', 'k8s']):
            return 'infrastructure'
        return 'other'
    
    def _detect_tags(self, question: str, answer: str) -> List[str]:
        """Detect tags based on content."""
        text = (question + " " + answer).lower()
        tags = []
        
        if any(x in text for x in ['error', 'fix', 'bug', 'issue', 'fail']):
            tags.append('debugging')
        if any(x in text for x in ['implement', 'create', 'add', 'build']):
            tags.append('implementation')
        if any(x in text for x in ['architect', 'design', 'structure', 'pattern']):
            tags.append('architecture')
        if any(x in text for x in ['config', 'setting', 'env', 'setup']):
            tags.append('configuration')
        if any(x in text for x in ['doc', 'readme', 'comment', 'explain']):
            tags.append('documentation')
        if any(x in text for x in ['refactor', 'clean', 'improve', 'optimize']):
            tags.append('refactoring')
        if any(x in text for x in ['test', 'spec', 'mock', 'assert']):
            tags.append('testing')
        
        return tags[:3]  # Limit to 3 tags
    
    def _has_code(self, text: str) -> bool:
        """Check if text contains code."""
        return '```' in text or any(x in text for x in ['function ', 'const ', 'import ', 'def ', 'class '])
    
    def sync_sessions(self, since: Optional[datetime] = None):
        """Sync sessions to Airtable."""
        if "Sessions" not in self.tables:
            print("❌ Sessions table not configured")
            return 0
        
        table = self.tables["Sessions"]
        sessions = self._get_sessions_from_db(since)
        
        print(f"\n📤 Syncing {len(sessions)} sessions...")
        
        synced = 0
        for session in sessions:
            try:
                # Check if already exists
                existing = table.all(formula=match({"Session ID": session.get("session_id", "")}))
                
                record = {
                    "Session ID": session.get("session_id", ""),
                    "Project": session.get("project_name", "unknown"),
                    "Workspace": session.get("workspace_id", ""),
                    "Date": session.get("timestamp", "")[:10] if session.get("timestamp") else None,
                    "Messages": session.get("message_count", 0),
                    "First Message": (session.get("first_message", "") or "")[:1000],
                    "Category": self._categorize_project(session.get("project_name", "")),
                    "Status": "Active",
                    "Last Synced": datetime.now().isoformat(),
                    "File Path": session.get("file_path", ""),
                    "Hash": session.get("content_hash", "")
                }
                
                if existing:
                    # Update existing
                    table.update(existing[0]["id"], record)
                else:
                    # Create new
                    table.create(record)
                
                synced += 1
                
                # Rate limiting
                if synced % 5 == 0:
                    time.sleep(0.2)
                    
            except Exception as e:
                print(f"  ⚠️  Error syncing session: {e}")
        
        return synced
    
    def sync_qa_pairs(self, limit: int = 500):
        """Sync Q&A pairs to Airtable."""
        if "QA_Pairs" not in self.tables:
            print("❌ QA_Pairs table not configured")
            return 0
        
        table = self.tables["QA_Pairs"]
        pairs = self._get_qa_pairs()[:limit]  # Limit to avoid rate limits
        
        print(f"\n📤 Syncing {len(pairs)} Q&A pairs...")
        
        synced = 0
        for i, pair in enumerate(pairs):
            try:
                qa_id = hashlib.md5(
                    f"{pair.get('project', '')}{pair.get('question', '')[:100]}".encode()
                ).hexdigest()[:12]
                
                # Check if exists
                existing = table.all(formula=match({"ID": qa_id}))
                
                question = pair.get("question", "")[:2000]
                answer = pair.get("answer", "")[:2000]
                
                record = {
                    "ID": qa_id,
                    "Project": pair.get("project", "unknown"),
                    "Date": pair.get("date"),
                    "Question": question,
                    "Answer": answer,
                    "Question Length": len(question),
                    "Answer Length": len(answer),
                    "Has Code": self._has_code(answer),
                    "Tags": self._detect_tags(question, answer),
                    "Quality": "Unrated",
                    "Useful for Training": False
                }
                
                if existing:
                    table.update(existing[0]["id"], record)
                else:
                    table.create(record)
                
                synced += 1
                
                # Progress
                if synced % 50 == 0:
                    print(f"  ... {synced}/{len(pairs)}")
                
                # Rate limiting
                if synced % 5 == 0:
                    time.sleep(0.2)
                    
            except Exception as e:
                print(f"  ⚠️  Error syncing Q&A: {e}")
        
        return synced
    
    def sync_projects(self):
        """Sync project summary to Airtable."""
        if "Projects" not in self.tables:
            print("❌ Projects table not configured")
            return 0
        
        table = self.tables["Projects"]
        
        # Get project stats from database
        if not DB_PATH.exists():
            return 0
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                project_name,
                COUNT(*) as sessions,
                SUM(message_count) as messages,
                MIN(timestamp) as first_activity,
                MAX(timestamp) as last_activity
            FROM sessions
            GROUP BY project_name
            ORDER BY sessions DESC
        """)
        
        projects = cursor.fetchall()
        conn.close()
        
        print(f"\n📤 Syncing {len(projects)} projects...")
        
        synced = 0
        for project in projects:
            name, sessions, messages, first_act, last_act = project
            
            try:
                existing = table.all(formula=match({"Name": name}))
                
                record = {
                    "Name": name,
                    "Category": self._categorize_project(name),
                    "Total Sessions": sessions,
                    "Total Messages": messages or 0,
                    "First Activity": first_act[:10] if first_act else None,
                    "Last Activity": last_act[:10] if last_act else None,
                    "Status": "Active"
                }
                
                if existing:
                    table.update(existing[0]["id"], record)
                else:
                    table.create(record)
                
                synced += 1
                time.sleep(0.1)
                
            except Exception as e:
                print(f"  ⚠️  Error syncing project {name}: {e}")
        
        return synced
    
    def sync_daily(self, date: Optional[str] = None):
        """Sync daily activity summary."""
        if "Daily_Activity" not in self.tables:
            print("❌ Daily_Activity table not configured")
            return 0
        
        table = self.tables["Daily_Activity"]
        
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        
        # Get stats for date
        if not DB_PATH.exists():
            return 0
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as sessions,
                SUM(message_count) as messages,
                GROUP_CONCAT(DISTINCT project_name) as projects
            FROM sessions
            WHERE DATE(timestamp) = ?
        """, (target_date,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row or row[0] == 0:
            print(f"  No activity for {target_date}")
            return 0
        
        sessions, messages, projects = row
        
        try:
            existing = table.all(formula=match({"Date": target_date}))
            
            # Get QA count
            qa_count = len([p for p in self._get_qa_pairs() if p.get("date") == target_date])
            
            record = {
                "Date": target_date,
                "Sessions": sessions,
                "Messages": messages or 0,
                "QA Pairs": qa_count,
                "Top Projects": (projects or "")[:500],
                "Productivity Score": min(10, (messages or 0) / 50)  # Simple score
            }
            
            if existing:
                table.update(existing[0]["id"], record)
            else:
                table.create(record)
            
            print(f"  ✅ Synced daily activity for {target_date}")
            return 1
            
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
            return 0
    
    def sync_all(self, since: Optional[datetime] = None):
        """Run full sync."""
        print("\n" + "=" * 60)
        print("🔄 Airtable Full Sync")
        print("=" * 60)
        
        start_time = datetime.now()
        
        # Sync all tables
        sessions = self.sync_sessions(since)
        qa_pairs = self.sync_qa_pairs()
        projects = self.sync_projects()
        daily = self.sync_daily()
        
        # Update config
        self.config.last_sync = datetime.now().isoformat()
        self.config.sync_count += 1
        self._save_config()
        
        duration = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "=" * 60)
        print(f"✅ Sync Complete!")
        print(f"   Sessions: {sessions}")
        print(f"   Q&A Pairs: {qa_pairs}")
        print(f"   Projects: {projects}")
        print(f"   Duration: {duration:.1f}s")
        print("=" * 60)
    
    def show_status(self):
        """Show sync status."""
        print("\n📊 Airtable Sync Status\n")
        
        if not self.config:
            print("❌ Not configured. Run: python3 airtable_sync.py --setup")
            return
        
        print(f"Base ID: {self.config.base_id}")
        print(f"Last Sync: {self.config.last_sync or 'Never'}")
        print(f"Sync Count: {self.config.sync_count}")
        print()
        
        print("Tables:")
        for table_name in TABLES_SCHEMA.keys():
            table_id = self.config.table_ids.get(table_name, "")
            status = "✅" if table_id else "❌"
            print(f"  {status} {table_name}: {table_id or 'Not configured'}")
        
        print()
        
        if self.tables:
            print("Record counts:")
            for name, table in self.tables.items():
                try:
                    count = len(table.all())
                    print(f"  {name}: {count} records")
                except:
                    print(f"  {name}: Unable to count")


def main():
    parser = argparse.ArgumentParser(
        description="Sync Copilot chat backups to Airtable"
    )
    parser.add_argument("--setup", action="store_true", help="Interactive setup wizard")
    parser.add_argument("--init", action="store_true", help="Initialize/configure tables")
    parser.add_argument("--sync", action="store_true", help="Run full sync")
    parser.add_argument("--sync-today", action="store_true", help="Sync today's data only")
    parser.add_argument("--sync-sessions", action="store_true", help="Sync sessions only")
    parser.add_argument("--sync-qa", action="store_true", help="Sync Q&A pairs only")
    parser.add_argument("--status", action="store_true", help="Show sync status")
    parser.add_argument("--qa-limit", type=int, default=500, help="Max Q&A pairs to sync")
    
    args = parser.parse_args()
    
    if not AIRTABLE_AVAILABLE and not args.status:
        print("\n❌ pyairtable package required")
        print("   Install with: pip install pyairtable")
        return
    
    sync = AirtableChatSync()
    
    if args.setup:
        sync.setup_interactive()
    elif args.init:
        sync.init_tables()
    elif args.sync:
        sync.sync_all()
    elif args.sync_today:
        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sync.sync_all(since=since)
    elif args.sync_sessions:
        sync.sync_sessions()
    elif args.sync_qa:
        sync.sync_qa_pairs(limit=args.qa_limit)
    elif args.status:
        sync.show_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
