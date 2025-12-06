#!/usr/bin/env python3
"""
GitHub Copilot Chat Backup System - Enhanced Version
=====================================================
Comprehensive backup system that captures ALL chat sessions from:
- All VS Code workspaces
- All project worktrees
- All .code-workspace files
- Remote/Codespace sessions

Features:
- Multi-schedule backups (hourly, daily, weekly)
- Incremental backups with change detection
- Project-aware organization
- AI-friendly export formats
- Activity tracking and analytics

Usage:
    python backup-all-chats.py                     # Full backup
    python backup-all-chats.py --incremental       # Only new/changed
    python backup-all-chats.py --schedule hourly   # Mark as hourly backup
    python backup-all-chats.py --list              # List all workspaces
"""

import json
import shutil
import hashlib
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import re
import urllib.parse

# ============================================================================
# Configuration
# ============================================================================

VSCODE_STORAGE_PATH = Path.home() / ".config/Code/User/workspaceStorage"
BACKUP_ROOT = Path.home() / "copilot-chat-backups"

# All known project directories (auto-discovered + manual)
PROJECT_ROOTS = [
    "/mnt/NTFS-Data/GitHub-SSD",
    str(Path.home()),
]

# Project name patterns for categorization
PROJECT_PATTERNS = {
    "aiconnects-hub": ["aiconnects-hub"],
    "aiconnects-worktrees": ["aiconnects-ws-", "aiconnects-codex", "aiconnects-copilot", 
                             "aiconnects-frontend", "aiconnects-seo", "aiconnects-writer",
                             "aiconnects-workflow"],
    "smart-spending-hub": ["smart-spending-hub", "smart-hub"],
    "howaiconnects": ["howaiconnects"],
    "aiconnects-legacy": ["aiconnects/", "aiconnects.code-workspace"],
}


@dataclass
class WorkspaceInfo:
    """Information about a VS Code workspace."""
    workspace_id: str
    workspace_path: str
    workspace_type: str  # 'folder', 'workspace', 'remote'
    project_name: str
    project_category: str
    chat_sessions_dir: Path
    chat_files: List[Path] = field(default_factory=list)
    total_size: int = 0
    last_modified: Optional[datetime] = None


@dataclass
class BackupStats:
    """Backup operation statistics."""
    timestamp: datetime
    schedule_type: str
    total_workspaces: int = 0
    total_sessions: int = 0
    total_messages: int = 0
    new_sessions: int = 0
    updated_sessions: int = 0
    total_size_bytes: int = 0
    duration_seconds: float = 0
    projects: Dict[str, int] = field(default_factory=dict)


class CopilotBackupSystem:
    """Comprehensive Copilot chat backup system."""
    
    def __init__(self, backup_root: Optional[Path] = None):
        self.backup_root = backup_root or BACKUP_ROOT
        self.backup_root.mkdir(parents=True, exist_ok=True)
        
        # Directory structure
        self.dirs = {
            'raw': self.backup_root / 'raw',
            'markdown': self.backup_root / 'markdown', 
            'daily': self.backup_root / 'daily',
            'hourly': self.backup_root / 'hourly',
            'ai_export': self.backup_root / 'ai-export',
            'index': self.backup_root / 'index',
            'archive': self.backup_root / 'archive',
            'logs': self.backup_root / 'logs',
        }
        for d in self.dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        
        # Database for tracking
        self.db_path = self.backup_root / 'backup_tracking.db'
        self._init_database()
        
        # Discover all workspaces
        self.workspaces = self._discover_all_workspaces()
    
    def _init_database(self):
        """Initialize SQLite database for tracking backups."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                workspace_id TEXT,
                project_name TEXT,
                file_hash TEXT,
                file_size INTEGER,
                message_count INTEGER,
                first_seen TEXT,
                last_updated TEXT,
                last_backup TEXT
            );
            
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                schedule_type TEXT,
                total_sessions INTEGER,
                new_sessions INTEGER,
                updated_sessions INTEGER,
                total_size INTEGER,
                duration_seconds REAL
            );
            
            CREATE TABLE IF NOT EXISTS daily_activity (
                date TEXT PRIMARY KEY,
                total_sessions INTEGER,
                total_messages INTEGER,
                projects TEXT,
                topics TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_name);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(last_updated);
        ''')
        
        conn.commit()
        conn.close()
    
    def _categorize_project(self, path: str) -> tuple:
        """Categorize a workspace path into project name and category."""
        path_lower = path.lower()
        
        # Decode URL encoding
        path_decoded = urllib.parse.unquote(path)
        
        for category, patterns in PROJECT_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in path_lower or pattern.lower() in path_decoded.lower():
                    # Extract specific project name
                    parts = path_decoded.replace('file://', '').split('/')
                    for part in reversed(parts):
                        if part and not part.endswith('.code-workspace'):
                            return part, category
                    return pattern, category
        
        # Default: use folder/file name
        path_clean = path_decoded.replace('file://', '')
        name = Path(path_clean).stem if path_clean else 'unknown'
        return name, 'other'
    
    def _discover_all_workspaces(self) -> Dict[str, WorkspaceInfo]:
        """Discover all VS Code workspaces with chat sessions."""
        workspaces = {}
        
        if not VSCODE_STORAGE_PATH.exists():
            print(f"⚠️ VS Code storage not found: {VSCODE_STORAGE_PATH}")
            return workspaces
        
        for ws_dir in VSCODE_STORAGE_PATH.iterdir():
            if not ws_dir.is_dir():
                continue
            
            workspace_json = ws_dir / "workspace.json"
            chat_sessions_dir = ws_dir / "chatSessions"
            
            if not chat_sessions_dir.exists():
                continue
            
            chat_files = list(chat_sessions_dir.glob("*.json"))
            if not chat_files:
                continue
            
            # Parse workspace info
            ws_path = ""
            ws_type = "folder"
            
            if workspace_json.exists():
                try:
                    with open(workspace_json, 'r') as f:
                        data = json.load(f)
                    ws_path = data.get('folder') or data.get('workspace', '')
                    ws_type = 'workspace' if 'workspace' in data else 'folder'
                    
                    # Check for remote
                    if 'vscode-remote' in ws_path or 'codespaces' in ws_path:
                        ws_type = 'remote'
                except Exception:
                    pass
            
            project_name, project_category = self._categorize_project(ws_path)
            
            # Calculate stats
            total_size = sum(f.stat().st_size for f in chat_files)
            latest_mod = max(f.stat().st_mtime for f in chat_files) if chat_files else 0
            
            workspaces[ws_dir.name] = WorkspaceInfo(
                workspace_id=ws_dir.name,
                workspace_path=ws_path,
                workspace_type=ws_type,
                project_name=project_name,
                project_category=project_category,
                chat_sessions_dir=chat_sessions_dir,
                chat_files=chat_files,
                total_size=total_size,
                last_modified=datetime.fromtimestamp(latest_mod) if latest_mod else None,
            )
        
        return workspaces
    
    def _get_file_hash(self, filepath: Path) -> str:
        """Calculate MD5 hash of a file."""
        return hashlib.md5(filepath.read_bytes()).hexdigest()
    
    def _parse_session(self, filepath: Path) -> Dict[str, Any]:
        """Parse a chat session file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            messages = []
            for req in data.get('requests', []):
                # User message
                user_msg = req.get('message', {})
                user_text = user_msg.get('text', '') if isinstance(user_msg, dict) else str(user_msg)
                if user_text:
                    messages.append({'role': 'user', 'content': user_text})
                
                # Assistant response
                response = req.get('response', {})
                if isinstance(response, dict):
                    resp_text = response.get('value', '') or response.get('result', {}).get('value', '')
                    if resp_text:
                        messages.append({'role': 'assistant', 'content': resp_text})
            
            # Parse timestamps
            creation = data.get('creationDate', 0)
            last_msg = data.get('lastMessageDate', creation)
            if creation > 1e12:
                creation /= 1000
            if last_msg > 1e12:
                last_msg /= 1000
            
            return {
                'session_id': data.get('sessionId', filepath.stem),
                'creation_date': datetime.fromtimestamp(creation).isoformat() if creation else None,
                'last_message_date': datetime.fromtimestamp(last_msg).isoformat() if last_msg else None,
                'requester': data.get('requesterUsername', 'user'),
                'responder': data.get('responderUsername', 'GitHub Copilot'),
                'messages': messages,
                'message_count': len(messages),
            }
        except Exception as e:
            print(f"  ⚠️ Error parsing {filepath.name}: {e}")
            return None
    
    def backup(self, schedule_type: str = 'manual', incremental: bool = False) -> BackupStats:
        """Perform backup of all chat sessions."""
        start_time = datetime.now()
        stats = BackupStats(timestamp=start_time, schedule_type=schedule_type)
        
        print(f"\n{'='*60}")
        print(f"🔄 Copilot Chat Backup - {schedule_type.upper()}")
        print(f"   Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        all_sessions = []
        
        for ws_id, ws_info in self.workspaces.items():
            stats.total_workspaces += 1
            project_sessions = 0
            
            for chat_file in ws_info.chat_files:
                file_hash = self._get_file_hash(chat_file)
                file_size = chat_file.stat().st_size
                
                # Check if already backed up (for incremental)
                if incremental:
                    cursor.execute(
                        'SELECT file_hash FROM sessions WHERE session_id = ?',
                        (chat_file.stem,)
                    )
                    existing = cursor.fetchone()
                    if existing and existing[0] == file_hash:
                        continue  # Skip unchanged
                
                # Parse session
                session = self._parse_session(chat_file)
                if not session:
                    continue
                
                session['workspace_id'] = ws_id
                session['project_name'] = ws_info.project_name
                session['project_category'] = ws_info.project_category
                session['file_path'] = str(chat_file)
                session['file_size'] = file_size
                
                all_sessions.append(session)
                stats.total_sessions += 1
                stats.total_messages += session['message_count']
                stats.total_size_bytes += file_size
                project_sessions += 1
                
                # Track in database
                cursor.execute('''
                    INSERT OR REPLACE INTO sessions 
                    (session_id, workspace_id, project_name, file_hash, file_size, 
                     message_count, first_seen, last_updated, last_backup)
                    VALUES (?, ?, ?, ?, ?, ?, 
                            COALESCE((SELECT first_seen FROM sessions WHERE session_id = ?), ?),
                            ?, ?)
                ''', (
                    session['session_id'], ws_id, ws_info.project_name, file_hash, file_size,
                    session['message_count'], session['session_id'], start_time.isoformat(),
                    session['last_message_date'], start_time.isoformat()
                ))
                
                # Backup raw file
                self._backup_raw_file(chat_file, ws_info.project_name, ws_info.project_category)
            
            if project_sessions > 0:
                stats.projects[ws_info.project_name] = stats.projects.get(ws_info.project_name, 0) + project_sessions
                print(f"  📁 {ws_info.project_name}: {project_sessions} sessions")
        
        conn.commit()
        
        # Generate exports
        if all_sessions:
            print(f"\n📝 Generating exports...")
            self._generate_markdown(all_sessions)
            self._generate_daily_summary(all_sessions, schedule_type)
            self._generate_ai_export(all_sessions)
            self._generate_master_index(all_sessions, stats)
        
        # Record backup
        stats.duration_seconds = (datetime.now() - start_time).total_seconds()
        cursor.execute('''
            INSERT INTO backups (timestamp, schedule_type, total_sessions, 
                                new_sessions, updated_sessions, total_size, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (start_time.isoformat(), schedule_type, stats.total_sessions,
              stats.new_sessions, stats.updated_sessions, 
              stats.total_size_bytes, stats.duration_seconds))
        
        conn.commit()
        conn.close()
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"✅ Backup Complete!")
        print(f"   Workspaces: {stats.total_workspaces}")
        print(f"   Sessions: {stats.total_sessions}")
        print(f"   Messages: {stats.total_messages}")
        print(f"   Size: {stats.total_size_bytes / (1024*1024):.2f} MB")
        print(f"   Duration: {stats.duration_seconds:.1f}s")
        print(f"{'='*60}\n")
        
        return stats
    
    def _backup_raw_file(self, filepath: Path, project_name: str, category: str):
        """Backup raw JSON file with organization."""
        # Organize by category/project/date
        date_str = datetime.now().strftime("%Y-%m-%d")
        dest_dir = self.dirs['raw'] / category / project_name / date_str
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        dest_file = dest_dir / filepath.name
        
        # Only copy if different
        if dest_file.exists():
            if self._get_file_hash(dest_file) == self._get_file_hash(filepath):
                return
        
        shutil.copy2(filepath, dest_file)
    
    def _generate_markdown(self, sessions: List[Dict]):
        """Generate readable markdown for each session."""
        for session in sessions:
            project_dir = self.dirs['markdown'] / session['project_category'] / session['project_name']
            project_dir.mkdir(parents=True, exist_ok=True)
            
            date = session.get('last_message_date', '')[:10] or 'unknown'
            filename = f"{date}_{session['session_id'][:8]}.md"
            filepath = project_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# Copilot Chat - {session['project_name']}\n\n")
                f.write(f"**Session ID:** `{session['session_id']}`\n")
                f.write(f"**Created:** {session.get('creation_date', 'N/A')}\n")
                f.write(f"**Last Message:** {session.get('last_message_date', 'N/A')}\n")
                f.write(f"**Messages:** {session['message_count']}\n\n")
                f.write("---\n\n")
                
                for msg in session.get('messages', []):
                    icon = "👤 **User**" if msg['role'] == 'user' else "🤖 **Copilot**"
                    f.write(f"## {icon}\n\n")
                    f.write(f"{msg['content']}\n\n")
                    f.write("---\n\n")
    
    def _generate_daily_summary(self, sessions: List[Dict], schedule_type: str):
        """Generate daily or hourly activity summary."""
        now = datetime.now()
        
        if schedule_type == 'hourly':
            filename = f"{now.strftime('%Y-%m-%d_%H')}00.md"
            target_dir = self.dirs['hourly']
            title = f"Hourly Activity - {now.strftime('%Y-%m-%d %H:00')}"
        else:
            filename = f"{now.strftime('%Y-%m-%d')}.md"
            target_dir = self.dirs['daily']
            title = f"Daily Activity - {now.strftime('%Y-%m-%d')}"
        
        # Group by project
        by_project = defaultdict(list)
        for s in sessions:
            by_project[s['project_name']].append(s)
        
        filepath = target_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n\n")
            f.write(f"**Generated:** {now.isoformat()}\n")
            f.write(f"**Total Sessions:** {len(sessions)}\n")
            f.write(f"**Total Messages:** {sum(s['message_count'] for s in sessions)}\n\n")
            
            f.write("## Projects\n\n")
            for project, proj_sessions in sorted(by_project.items(), key=lambda x: -len(x[1])):
                msg_count = sum(s['message_count'] for s in proj_sessions)
                f.write(f"### {project}\n")
                f.write(f"- Sessions: {len(proj_sessions)}\n")
                f.write(f"- Messages: {msg_count}\n\n")
                
                # Show recent topics
                for s in proj_sessions[:3]:
                    for msg in s.get('messages', []):
                        if msg['role'] == 'user':
                            preview = msg['content'][:150].replace('\n', ' ')
                            f.write(f"> {preview}...\n\n")
                            break
    
    def _generate_ai_export(self, sessions: List[Dict]):
        """Generate AI-friendly export formats."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        
        # Full export
        export_data = {
            'export_date': datetime.now().isoformat(),
            'total_sessions': len(sessions),
            'sessions': []
        }
        
        qa_pairs = []
        
        for session in sessions:
            session_export = {
                'id': session['session_id'],
                'project': session['project_name'],
                'category': session['project_category'],
                'created': session.get('creation_date'),
                'last_message': session.get('last_message_date'),
                'message_count': session['message_count'],
                'conversation': session.get('messages', [])
            }
            export_data['sessions'].append(session_export)
            
            # Extract Q&A pairs
            messages = session.get('messages', [])
            for i in range(0, len(messages) - 1, 2):
                if messages[i]['role'] == 'user' and i + 1 < len(messages):
                    qa_pairs.append({
                        'project': session['project_name'],
                        'date': session.get('last_message_date', '')[:10],
                        'question': messages[i]['content'],
                        'answer': messages[i + 1]['content'],
                    })
        
        # Write full export (latest)
        with open(self.dirs['ai_export'] / 'latest_export.json', 'w') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        # Write timestamped export
        with open(self.dirs['ai_export'] / f'export_{timestamp}.json', 'w') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        # Write Q&A pairs
        with open(self.dirs['ai_export'] / 'qa_pairs.json', 'w') as f:
            json.dump(qa_pairs, f, indent=2, ensure_ascii=False)
        
        with open(self.dirs['ai_export'] / 'qa_pairs.jsonl', 'w') as f:
            for qa in qa_pairs:
                f.write(json.dumps(qa, ensure_ascii=False) + '\n')
        
        # Write sessions JSONL
        with open(self.dirs['ai_export'] / 'sessions.jsonl', 'w') as f:
            for s in export_data['sessions']:
                f.write(json.dumps(s, ensure_ascii=False) + '\n')
        
        print(f"   📤 Exported {len(qa_pairs)} Q&A pairs")
    
    def _generate_master_index(self, sessions: List[Dict], stats: BackupStats):
        """Generate master index with all metadata."""
        index = {
            'generated': datetime.now().isoformat(),
            'stats': {
                'total_workspaces': stats.total_workspaces,
                'total_sessions': stats.total_sessions,
                'total_messages': stats.total_messages,
                'total_size_mb': stats.total_size_bytes / (1024 * 1024),
                'projects': dict(stats.projects),
            },
            'workspaces': {},
            'sessions': [],
        }
        
        # Add workspace info
        for ws_id, ws_info in self.workspaces.items():
            index['workspaces'][ws_id] = {
                'path': ws_info.workspace_path,
                'type': ws_info.workspace_type,
                'project': ws_info.project_name,
                'category': ws_info.project_category,
                'chat_count': len(ws_info.chat_files),
            }
        
        # Add session summaries
        for s in sessions:
            first_msg = ""
            for msg in s.get('messages', []):
                if msg['role'] == 'user':
                    first_msg = msg['content'][:200]
                    break
            
            index['sessions'].append({
                'id': s['session_id'],
                'project': s['project_name'],
                'category': s['project_category'],
                'last_message': s.get('last_message_date'),
                'message_count': s['message_count'],
                'preview': first_msg,
            })
        
        with open(self.dirs['index'] / 'master_index.json', 'w') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    
    def list_workspaces(self):
        """Print all discovered workspaces."""
        print("\n📂 Discovered VS Code Workspaces\n")
        print(f"{'Project':<30} {'Category':<20} {'Chats':<8} {'Size':<10} {'Type'}")
        print("=" * 90)
        
        # Sort by chat count
        sorted_ws = sorted(
            self.workspaces.values(),
            key=lambda w: len(w.chat_files),
            reverse=True
        )
        
        for ws in sorted_ws:
            size_mb = ws.total_size / (1024 * 1024)
            print(f"{ws.project_name:<30} {ws.project_category:<20} {len(ws.chat_files):<8} {size_mb:>6.2f} MB  {ws.workspace_type}")
        
        print(f"\nTotal: {len(self.workspaces)} workspaces, "
              f"{sum(len(w.chat_files) for w in self.workspaces.values())} chat sessions")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Backup all Copilot chat sessions')
    parser.add_argument('--schedule', '-s', choices=['hourly', 'daily', 'weekly', 'manual'],
                        default='manual', help='Backup schedule type')
    parser.add_argument('--incremental', '-i', action='store_true',
                        help='Only backup new/changed sessions')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all workspaces and exit')
    parser.add_argument('--backup-path', '-o', type=Path,
                        help='Custom backup destination')
    
    args = parser.parse_args()
    
    backup = CopilotBackupSystem(backup_root=args.backup_path)
    
    if args.list:
        backup.list_workspaces()
    else:
        backup.backup(schedule_type=args.schedule, incremental=args.incremental)


if __name__ == "__main__":
    main()
