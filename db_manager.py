#!/usr/bin/env python3
"""
Database manager for storing chat backup metrics locally in the repository.
Uses SQLite to persist all metrics, sessions, and workspace data.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BackupDatabase:
    """SQLite database manager for chat backup metrics."""
    
    def __init__(self, db_path: str = "copilot_backup.db"):
        """Initialize database connection."""
        self.db_path = Path(db_path)
        self.conn = None
        self.setup_database()
    
    def setup_database(self):
        """Create database tables if they don't exist."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        
        # Create tables
        self.conn.executescript("""
            -- Backup runs table
            CREATE TABLE IF NOT EXISTS backup_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total_sessions INTEGER NOT NULL,
                total_messages INTEGER NOT NULL,
                total_size_bytes INTEGER NOT NULL,
                total_workspaces INTEGER NOT NULL,
                duration_seconds REAL,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Sessions table
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_run_id INTEGER,
                session_id TEXT UNIQUE NOT NULL,
                project TEXT NOT NULL,
                message_count INTEGER NOT NULL,
                user_messages INTEGER NOT NULL,
                assistant_messages INTEGER NOT NULL,
                duration_seconds REAL,
                created_at TEXT NOT NULL,
                last_message_at TEXT NOT NULL,
                model TEXT,
                FOREIGN KEY (backup_run_id) REFERENCES backup_runs(id)
            );
            
            -- Workspaces table
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_run_id INTEGER,
                workspace_name TEXT NOT NULL,
                session_count INTEGER NOT NULL,
                total_messages INTEGER NOT NULL,
                avg_messages_per_session REAL,
                active_days INTEGER,
                first_session TEXT,
                last_session TEXT,
                FOREIGN KEY (backup_run_id) REFERENCES backup_runs(id)
            );
            
            -- Hourly activity table
            CREATE TABLE IF NOT EXISTS hourly_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_run_id INTEGER,
                hour INTEGER NOT NULL,
                message_count INTEGER NOT NULL,
                FOREIGN KEY (backup_run_id) REFERENCES backup_runs(id)
            );
            
            -- Daily activity table
            CREATE TABLE IF NOT EXISTS daily_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_run_id INTEGER,
                date TEXT NOT NULL,
                message_count INTEGER NOT NULL,
                FOREIGN KEY (backup_run_id) REFERENCES backup_runs(id)
            );
            
            -- Create indexes
            CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions(session_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
            CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);
            CREATE INDEX IF NOT EXISTS idx_workspaces_name ON workspaces(workspace_name);
            CREATE INDEX IF NOT EXISTS idx_daily_activity_date ON daily_activity(date);

            -- Chat content tables
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                workspace_id TEXT,
                workspace_name TEXT NOT NULL,
                workspace_path TEXT,
                project_name TEXT,
                creation_date TEXT,
                last_message_date TEXT,
                requester_username TEXT,
                responder_username TEXT,
                message_count INTEGER NOT NULL,
                file_path TEXT,
                file_size INTEGER,
                file_hash TEXT,
                synced_at TEXT NOT NULL,
                session_type TEXT DEFAULT 'conversation',
                edit_file_paths TEXT,
                edit_line_count INTEGER DEFAULT 0,
                edit_files_count INTEGER DEFAULT 0,
                custom_title TEXT,
                initial_location TEXT,
                mode_id TEXT,
                mode_kind TEXT,
                selected_model_identifier TEXT,
                selected_model_name TEXT,
                selected_model_vendor TEXT,
                selected_model_family TEXT,
                request_model_id TEXT,
                agent_id TEXT,
                agent_name TEXT,
                has_pending_edits INTEGER,
                input_text TEXT,
                attachments_count INTEGER,
                selections_count INTEGER,
                content_references_count INTEGER,
                code_citations_count INTEGER,
                repo_name TEXT,
                repo_owner TEXT,
                repo_branch TEXT,
                repo_default_branch TEXT
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER,
                model TEXT,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS chat_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                total_sessions INTEGER NOT NULL,
                inserted_sessions INTEGER NOT NULL,
                updated_sessions INTEGER NOT NULL,
                skipped_sessions INTEGER NOT NULL,
                errors INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chat_sessions_workspace ON chat_sessions(workspace_name);
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_project ON chat_sessions(project_name);
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_message ON chat_sessions(last_message_date);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
        """)
        
        self.conn.commit()
        self._ensure_chat_sessions_columns()
        logger.info(f"Database initialized at {self.db_path}")

    def _ensure_chat_sessions_columns(self):
        """Ensure new metadata columns exist on chat_sessions table."""
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(chat_sessions)")
        existing = {row[1] for row in cursor.fetchall()}

        desired_columns = {
            "custom_title": "TEXT",
            "initial_location": "TEXT",
            "mode_id": "TEXT",
            "mode_kind": "TEXT",
            "selected_model_identifier": "TEXT",
            "selected_model_name": "TEXT",
            "selected_model_vendor": "TEXT",
            "selected_model_family": "TEXT",
            "request_model_id": "TEXT",
            "agent_id": "TEXT",
            "agent_name": "TEXT",
            "has_pending_edits": "INTEGER",
            "input_text": "TEXT",
            "attachments_count": "INTEGER",
            "selections_count": "INTEGER",
            "content_references_count": "INTEGER",
            "code_citations_count": "INTEGER",
            "repo_name": "TEXT",
            "repo_owner": "TEXT",
            "repo_branch": "TEXT",
            "repo_default_branch": "TEXT",
            "session_type": "TEXT",
            "edit_file_paths": "TEXT",
            "edit_line_count": "INTEGER",
            "edit_files_count": "INTEGER",
        }

        for column, col_type in desired_columns.items():
            if column not in existing:
                cursor.execute(
                    f"ALTER TABLE chat_sessions ADD COLUMN {column} {col_type}"
                )

        self.conn.commit()
    
    def save_backup_run(self, metrics: Dict[str, Any]) -> int:
        """Save a complete backup run with all metrics."""
        cursor = self.conn.cursor()
        
        # Save backup run summary
        cursor.execute("""
            INSERT INTO backup_runs 
            (timestamp, total_sessions, total_messages, total_size_bytes, total_workspaces)
            VALUES (?, ?, ?, ?, ?)
        """, (
            metrics.get('timestamp'),
            metrics['totals']['sessions'],
            metrics['totals']['messages'],
            metrics['totals']['size_bytes'],
            metrics['totals']['workspaces']
        ))
        
        backup_run_id = cursor.lastrowid
        
        # Save sessions
        for session in metrics.get('sessions', []):
            cursor.execute("""
                INSERT OR REPLACE INTO sessions 
                (backup_run_id, session_id, project, message_count, user_messages, 
                 assistant_messages, duration_seconds, created_at, last_message_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                backup_run_id,
                session['session_id'],
                session['project'],
                session['message_count'],
                session['user_messages'],
                session['assistant_messages'],
                session['duration_seconds'],
                session['created_at'],
                session['last_message_at']
            ))
        
        # Save workspaces
        for workspace_name, workspace_data in metrics.get('workspaces', {}).items():
            cursor.execute("""
                INSERT INTO workspaces 
                (backup_run_id, workspace_name, session_count, total_messages, 
                 avg_messages_per_session, active_days, first_session, last_session)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                backup_run_id,
                workspace_name,
                workspace_data['session_count'],
                workspace_data['total_messages'],
                workspace_data['avg_messages_per_session'],
                workspace_data['active_days'],
                workspace_data['first_session'],
                workspace_data['last_session']
            ))
        
        # Save hourly activity
        for hour, count in metrics.get('temporal', {}).get('hourly', {}).items():
            cursor.execute("""
                INSERT INTO hourly_activity (backup_run_id, hour, message_count)
                VALUES (?, ?, ?)
            """, (backup_run_id, int(hour), count))
        
        # Save daily activity
        for date, count in metrics.get('temporal', {}).get('daily', {}).items():
            cursor.execute("""
                INSERT INTO daily_activity (backup_run_id, date, message_count)
                VALUES (?, ?, ?)
            """, (backup_run_id, date, count))
        
        self.conn.commit()
        logger.info(f"Saved backup run #{backup_run_id} with {len(metrics.get('sessions', []))} sessions")
        
        return backup_run_id
    
    def get_latest_backup(self) -> Optional[Dict]:
        """Get the most recent backup run."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM backup_runs ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_workspace_history(self, workspace_name: str) -> List[Dict]:
        """Get historical data for a specific workspace."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT w.*, b.timestamp 
            FROM workspaces w
            JOIN backup_runs b ON w.backup_run_id = b.id
            WHERE w.workspace_name = ?
            ORDER BY b.timestamp DESC
        """, (workspace_name,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_activity_trend(self, days: int = 30) -> List[Dict]:
        """Get activity trend over the last N days."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT date, SUM(message_count) as total_messages
            FROM daily_activity
            WHERE date >= date('now', '-' || ? || ' days')
            GROUP BY date
            ORDER BY date
        """, (days,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_top_workspaces(self, limit: int = 10) -> List[Dict]:
        """Get top workspaces by total messages from latest backup."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT w.* 
            FROM workspaces w
            JOIN backup_runs b ON w.backup_run_id = b.id
            WHERE b.id = (SELECT MAX(id) FROM backup_runs)
            ORDER BY w.total_messages DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_stats_summary(self) -> Dict:
        """Get overall statistics summary."""
        cursor = self.conn.cursor()
        
        # Get latest backup stats
        latest = self.get_latest_backup()
        
        # Get backup count
        cursor.execute("SELECT COUNT(*) as count FROM backup_runs")
        backup_count = cursor.fetchone()['count']
        
        # Get total unique sessions
        cursor.execute("SELECT COUNT(DISTINCT session_id) as count FROM sessions")
        unique_sessions = cursor.fetchone()['count']
        
        # Get date range
        cursor.execute("""
            SELECT MIN(created_at) as first_backup, MAX(created_at) as last_backup 
            FROM backup_runs
        """)
        date_range = dict(cursor.fetchone())
        
        return {
            'latest_backup': latest,
            'total_backups': backup_count,
            'unique_sessions': unique_sessions,
            'date_range': date_range
        }
    
    def export_to_json(self, output_file: str):
        """Export all data to JSON file."""
        data = {
            'backup_runs': [dict(row) for row in self.conn.execute("SELECT * FROM backup_runs").fetchall()],
            'sessions': [dict(row) for row in self.conn.execute("SELECT * FROM sessions").fetchall()],
            'workspaces': [dict(row) for row in self.conn.execute("SELECT * FROM workspaces").fetchall()],
            'export_timestamp': datetime.now().isoformat()
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported database to {output_file}")

    def get_chat_session_hash(self, session_id: str) -> Optional[str]:
        """Get stored file hash for a chat session."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT file_hash FROM chat_sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        return row['file_hash'] if row else None

    def upsert_chat_session(
        self,
        session: Dict[str, Any],
        messages: List[Dict[str, Any]],
        file_hash: str
    ) -> str:
        """Insert or update a chat session and its messages.

        Returns: 'inserted', 'updated', or 'skipped'.
        """
        session_id = session['session_id']
        existing_hash = self.get_chat_session_hash(session_id)

        if existing_hash and existing_hash == file_hash:
            return 'skipped'

        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        if existing_hash:
            cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            cursor.execute(
                """
                UPDATE chat_sessions SET
                    workspace_id = ?,
                    workspace_name = ?,
                    workspace_path = ?,
                    project_name = ?,
                    creation_date = ?,
                    last_message_date = ?,
                    requester_username = ?,
                    responder_username = ?,
                    message_count = ?,
                    file_path = ?,
                    file_size = ?,
                    file_hash = ?,
                    synced_at = ?,
                    custom_title = ?,
                    initial_location = ?,
                    mode_id = ?,
                    mode_kind = ?,
                    selected_model_identifier = ?,
                    selected_model_name = ?,
                    selected_model_vendor = ?,
                    selected_model_family = ?,
                    request_model_id = ?,
                    agent_id = ?,
                    agent_name = ?,
                    has_pending_edits = ?,
                    input_text = ?,
                    attachments_count = ?,
                    selections_count = ?,
                    content_references_count = ?,
                    code_citations_count = ?,
                    repo_name = ?,
                    repo_owner = ?,
                    repo_branch = ?,
                    repo_default_branch = ?,
                    session_type = ?,
                    edit_file_paths = ?,
                    edit_line_count = ?,
                    edit_files_count = ?
                WHERE session_id = ?
                """,
                (
                    session.get('workspace_id'),
                    session.get('workspace_name'),
                    session.get('workspace_path'),
                    session.get('project_name'),
                    session.get('creation_date'),
                    session.get('last_message_date'),
                    session.get('requester_username'),
                    session.get('responder_username'),
                    session.get('message_count'),
                    session.get('file_path'),
                    session.get('file_size'),
                    file_hash,
                    now,
                    session.get('custom_title'),
                    session.get('initial_location'),
                    session.get('mode_id'),
                    session.get('mode_kind'),
                    session.get('selected_model_identifier'),
                    session.get('selected_model_name'),
                    session.get('selected_model_vendor'),
                    session.get('selected_model_family'),
                    session.get('request_model_id'),
                    session.get('agent_id'),
                    session.get('agent_name'),
                    session.get('has_pending_edits'),
                    session.get('input_text'),
                    session.get('attachments_count'),
                    session.get('selections_count'),
                    session.get('content_references_count'),
                    session.get('code_citations_count'),
                    session.get('repo_name'),
                    session.get('repo_owner'),
                    session.get('repo_branch'),
                    session.get('repo_default_branch'),
                    session.get('session_type', 'conversation'),
                    session.get('edit_file_paths'),
                    session.get('edit_line_count', 0),
                    session.get('edit_files_count', 0),
                    session_id,
                )
            )
            status = 'updated'
        else:
            cursor.execute(
                """
                INSERT INTO chat_sessions (
                    session_id, workspace_id, workspace_name, workspace_path, project_name,
                    creation_date, last_message_date, requester_username, responder_username,
                    message_count, file_path, file_size, file_hash, synced_at,
                    custom_title, initial_location, mode_id, mode_kind,
                    selected_model_identifier, selected_model_name, selected_model_vendor, selected_model_family,
                    request_model_id, agent_id, agent_name, has_pending_edits, input_text,
                    attachments_count, selections_count, content_references_count, code_citations_count,
                    repo_name, repo_owner, repo_branch, repo_default_branch,
                    session_type, edit_file_paths, edit_line_count, edit_files_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    session.get('workspace_id'),
                    session.get('workspace_name'),
                    session.get('workspace_path'),
                    session.get('project_name'),
                    session.get('creation_date'),
                    session.get('last_message_date'),
                    session.get('requester_username'),
                    session.get('responder_username'),
                    session.get('message_count'),
                    session.get('file_path'),
                    session.get('file_size'),
                    file_hash,
                    now,
                    session.get('custom_title'),
                    session.get('initial_location'),
                    session.get('mode_id'),
                    session.get('mode_kind'),
                    session.get('selected_model_identifier'),
                    session.get('selected_model_name'),
                    session.get('selected_model_vendor'),
                    session.get('selected_model_family'),
                    session.get('request_model_id'),
                    session.get('agent_id'),
                    session.get('agent_name'),
                    session.get('has_pending_edits'),
                    session.get('input_text'),
                    session.get('attachments_count'),
                    session.get('selections_count'),
                    session.get('content_references_count'),
                    session.get('code_citations_count'),
                    session.get('repo_name'),
                    session.get('repo_owner'),
                    session.get('repo_branch'),
                    session.get('repo_default_branch'),
                    session.get('session_type', 'conversation'),
                    session.get('edit_file_paths'),
                    session.get('edit_line_count', 0),
                    session.get('edit_files_count', 0),
                )
            )
            status = 'inserted'

        for msg in messages:
            cursor.execute(
                """
                INSERT INTO chat_messages (session_id, position, role, content, timestamp, model)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    msg.get('position'),
                    msg.get('role'),
                    msg.get('content'),
                    msg.get('timestamp'),
                    msg.get('model'),
                )
            )

        self.conn.commit()
        return status

    def record_chat_sync_run(self, stats: Dict[str, Any]) -> int:
        """Record a chat sync run summary."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_sync_runs (
                started_at, finished_at, total_sessions, inserted_sessions,
                updated_sessions, skipped_sessions, errors
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stats['started_at'],
                stats['finished_at'],
                stats['total_sessions'],
                stats['inserted_sessions'],
                stats['updated_sessions'],
                stats['skipped_sessions'],
                stats['errors'],
            )
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_last_chat_sync_time(self) -> Optional[str]:
        """Get the most recent chat sync finished time."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT finished_at FROM chat_sync_runs ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return row['finished_at'] if row else None

    def get_chat_sessions_for_vectorization(self, workspace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return chat sessions with aggregated conversation text for vectorization."""
        cursor = self.conn.cursor()
        if workspace:
            cursor.execute(
                """
                SELECT * FROM chat_sessions
                WHERE LOWER(workspace_name) LIKE ? OR LOWER(project_name) LIKE ?
                ORDER BY last_message_date DESC
                """,
                (f"%{workspace.lower()}%", f"%{workspace.lower()}%")
            )
        else:
            cursor.execute(
                "SELECT * FROM chat_sessions ORDER BY last_message_date DESC"
            )

        sessions = [dict(row) for row in cursor.fetchall()]
        results: List[Dict[str, Any]] = []

        for session in sessions:
            cursor.execute(
                """
                SELECT role, content, timestamp, model, position
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY position ASC
                """,
                (session['session_id'],)
            )
            messages = [dict(row) for row in cursor.fetchall()]

            full_conversation = "\n---\n".join(m['content'] for m in messages if m.get('content'))
            title = ""
            for m in messages:
                if m.get('role') == 'user' and m.get('content'):
                    title = m['content'][:120]
                    break

            results.append({
                'session_id': session['session_id'],
                'workspace': session.get('workspace_name') or session.get('project_name'),
                'title': title or "Untitled",
                'start_time': session.get('creation_date'),
                'end_time': session.get('last_message_date'),
                'message_count': session.get('message_count', 0),
                'file_path': session.get('file_path', ''),
                'full_conversation': full_conversation,
                'messages': messages,
            })

        return results
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")


def main():
    """Command-line interface for database operations."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Manage copilot chat backup database')
    parser.add_argument('--stats', action='store_true', help='Show statistics summary')
    parser.add_argument('--top-workspaces', type=int, metavar='N', help='Show top N workspaces')
    parser.add_argument('--workspace', type=str, help='Show history for specific workspace')
    parser.add_argument('--trend', type=int, metavar='DAYS', help='Show activity trend for N days')
    parser.add_argument('--export', type=str, metavar='FILE', help='Export data to JSON file')
    parser.add_argument('--db', type=str, default='copilot_backup.db', help='Database file path')
    
    args = parser.parse_args()
    
    db = BackupDatabase(args.db)
    
    try:
        if args.stats:
            stats = db.get_stats_summary()
            print("\n📊 Database Statistics Summary")
            print("=" * 50)
            print(f"Total Backups: {stats['total_backups']}")
            print(f"Unique Sessions: {stats['unique_sessions']}")
            if stats['latest_backup']:
                latest = stats['latest_backup']
                print(f"\nLatest Backup:")
                print(f"  Timestamp: {latest['timestamp']}")
                print(f"  Sessions: {latest['total_sessions']}")
                print(f"  Messages: {latest['total_messages']}")
                print(f"  Workspaces: {latest['total_workspaces']}")
                print(f"  Size: {latest['total_size_bytes'] / 1024 / 1024:.2f} MB")
        
        elif args.top_workspaces:
            workspaces = db.get_top_workspaces(args.top_workspaces)
            print(f"\n🏢 Top {args.top_workspaces} Workspaces")
            print("=" * 70)
            for ws in workspaces:
                print(f"{ws['workspace_name']:30s} | {ws['total_messages']:5d} msgs | {ws['session_count']:3d} sessions")
        
        elif args.workspace:
            history = db.get_workspace_history(args.workspace)
            print(f"\n📈 History for workspace: {args.workspace}")
            print("=" * 70)
            for entry in history:
                print(f"{entry['timestamp']}: {entry['total_messages']} messages in {entry['session_count']} sessions")
        
        elif args.trend:
            trend = db.get_activity_trend(args.trend)
            print(f"\n📊 Activity Trend (Last {args.trend} days)")
            print("=" * 50)
            for day in trend:
                print(f"{day['date']}: {day['total_messages']} messages")
        
        elif args.export:
            db.export_to_json(args.export)
            print(f"✅ Exported to {args.export}")
        
        else:
            parser.print_help()
    
    finally:
        db.close()


if __name__ == '__main__':
    main()
