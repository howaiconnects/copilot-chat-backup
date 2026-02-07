#!/usr/bin/env python3
"""
GitHub Copilot Chat Backup System
==================================
Backs up all VS Code GitHub Copilot chat sessions to organized, AI-friendly formats.

Features:
- Discovers all workspaces and their chat sessions
- Extracts conversations into readable markdown
- Creates daily activity summaries
- Exports to JSON for AI analysis
- Maintains history with deduplication

Usage:
    python backup-copilot-chats.py                    # Full backup
    python backup-copilot-chats.py --workspace hub    # Specific workspace
    python backup-copilot-chats.py --daily            # Daily summary only
    python backup-copilot-chats.py --export-ai        # Export for AI analysis
"""

import json
import os
import shutil
import hashlib
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import re

# Configuration
# Try to find VS Code storage path
POSSIBLE_STORAGE_PATHS = [
    Path.home() / ".vscode-server/data/User/workspaceStorage",
    Path.home() / ".config/Code/User/workspaceStorage",
    Path.home() / "Library/Application Support/Code/User/workspaceStorage", # macOS
    Path.home() / ".config/Code - OSS/User/workspaceStorage", # OSS
]

VSCODE_STORAGE_PATH = None
for path in POSSIBLE_STORAGE_PATHS:
    if path.exists():
        VSCODE_STORAGE_PATH = path
        break

if not VSCODE_STORAGE_PATH:
    VSCODE_STORAGE_PATH = Path.home() / ".config/Code/User/workspaceStorage"

GLOBAL_STORAGE_PATH = Path.home() / ".config/Code/User/globalStorage/github.copilot-chat"
if (Path.home() / ".vscode-server/data/User/globalStorage/github.copilot-chat").exists():
    GLOBAL_STORAGE_PATH = Path.home() / ".vscode-server/data/User/globalStorage/github.copilot-chat"

DEFAULT_BACKUP_PATH = Path.home() / "copilot-chat-backups"

# Projects to track (add your workspace paths here)
TRACKED_PROJECTS = {
    "aiconnects-hub": "/mnt/NTFS-Data/GitHub-SSD/aiconnects-hub",
    "aiconnects-codex": "/mnt/NTFS-Data/GitHub-SSD/aiconnects-codex",
    "aiconnects-copilot": "/mnt/NTFS-Data/GitHub-SSD/aiconnects-copilot",
    "aiconnects-frontend": "/mnt/NTFS-Data/GitHub-SSD/aiconnects-frontend",
    "aiconnects-seo": "/mnt/NTFS-Data/GitHub-SSD/aiconnects-seo",
    "aiconnects-writer": "/mnt/NTFS-Data/GitHub-SSD/aiconnects-writer",
    "aiconnects-workflow": "/mnt/NTFS-Data/GitHub-SSD/aiconnects-workflow",
}


@dataclass
class ChatMessage:
    """Represents a single message in a chat conversation."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: Optional[int] = None
    model: Optional[str] = None
    

@dataclass
class ChatSession:
    """Represents a complete chat session."""
    session_id: str
    workspace_name: str
    workspace_path: str
    creation_date: datetime
    last_message_date: datetime
    requester_username: str
    responder_username: str
    messages: List[ChatMessage]
    file_path: str
    file_size: int
    message_count: int
    

@dataclass
class DailyActivity:
    """Daily activity summary."""
    date: str
    total_sessions: int
    total_messages: int
    projects: Dict[str, int]
    topics: List[str]
    files_modified: List[str]
    

class CopilotChatBackup:
    """Main backup system for GitHub Copilot chat sessions."""
    
    def __init__(self, backup_path: Optional[Path] = None):
        self.backup_path = backup_path or DEFAULT_BACKUP_PATH
        self.backup_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.raw_backup_path = self.backup_path / "raw"
        self.markdown_path = self.backup_path / "markdown"
        self.daily_path = self.backup_path / "daily"
        self.ai_export_path = self.backup_path / "ai-export"
        self.index_path = self.backup_path / "index"
        
        for path in [self.raw_backup_path, self.markdown_path, 
                     self.daily_path, self.ai_export_path, self.index_path]:
            path.mkdir(parents=True, exist_ok=True)
        
        self.workspace_map = self._discover_workspaces()
        
    def _discover_workspaces(self) -> Dict[str, Dict[str, Any]]:
        """Discover all VS Code workspaces and map them to projects."""
        workspace_map = {}
        
        if not VSCODE_STORAGE_PATH.exists():
            print(f"⚠️ VS Code storage path not found: {VSCODE_STORAGE_PATH}")
            return workspace_map
            
        for ws_dir in VSCODE_STORAGE_PATH.iterdir():
            if not ws_dir.is_dir():
                continue
                
            workspace_json = ws_dir / "workspace.json"
            if not workspace_json.exists():
                continue
                
            try:
                with open(workspace_json, 'r') as f:
                    ws_data = json.load(f)
                    
                # Get the workspace or folder path
                ws_path = ws_data.get('folder') or ws_data.get('workspace', '')
                ws_path = ws_path.replace('file://', '').replace('%20', ' ')
                ws_path = re.sub(r'%([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), ws_path)
                
                # Determine project name
                project_name = None
                for name, path in TRACKED_PROJECTS.items():
                    if path in ws_path or name in ws_path.lower():
                        project_name = name
                        break
                
                if not project_name:
                    # Extract name from path
                    project_name = Path(ws_path).stem if ws_path else ws_dir.name
                
                chat_sessions_dir = ws_dir / "chatSessions"
                chat_files = list(chat_sessions_dir.glob("*.json")) if chat_sessions_dir.exists() else []
                
                workspace_map[ws_dir.name] = {
                    'workspace_id': ws_dir.name,
                    'workspace_path': ws_path,
                    'project_name': project_name,
                    'chat_sessions_dir': chat_sessions_dir,
                    'chat_files': chat_files,
                    'chat_count': len(chat_files),
                }
                
            except (json.JSONDecodeError, KeyError) as e:
                print(f"⚠️ Error parsing workspace {ws_dir.name}: {e}")
                continue
                
        return workspace_map
    
    def _parse_chat_session(self, file_path: Path, workspace_info: Dict) -> Optional[ChatSession]:
        """Parse a single chat session file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            messages = []
            requests = data.get('requests', [])
            
            for req in requests:
                # User message
                user_msg = req.get('message', {})
                user_text = user_msg.get('text', '') if isinstance(user_msg, dict) else str(user_msg)
                
                if user_text:
                    messages.append(ChatMessage(
                        role='user',
                        content=user_text,
                        timestamp=req.get('timestamp'),
                    ))
                
                # Assistant response
                response = req.get('response', {})
                if isinstance(response, dict):
                    # Extract response text from various formats
                    response_text = ''
                    
                    # Try different response formats
                    if 'value' in response:
                        response_text = response['value']
                    elif 'result' in response:
                        result = response['result']
                        if isinstance(result, dict):
                            response_text = result.get('value', '') or result.get('message', '')
                        else:
                            response_text = str(result)
                    elif 'message' in response:
                        response_text = response['message']
                        
                    if response_text:
                        messages.append(ChatMessage(
                            role='assistant',
                            content=response_text,
                            model=response.get('model'),
                        ))
            
            # Parse timestamps
            creation_ts = data.get('creationDate', 0)
            last_msg_ts = data.get('lastMessageDate', creation_ts)
            
            # Handle millisecond timestamps
            if creation_ts > 1e12:
                creation_ts /= 1000
            if last_msg_ts > 1e12:
                last_msg_ts /= 1000
                
            return ChatSession(
                session_id=data.get('sessionId', file_path.stem),
                workspace_name=workspace_info.get('project_name', 'unknown'),
                workspace_path=workspace_info.get('workspace_path', ''),
                creation_date=datetime.fromtimestamp(creation_ts) if creation_ts else datetime.now(),
                last_message_date=datetime.fromtimestamp(last_msg_ts) if last_msg_ts else datetime.now(),
                requester_username=data.get('requesterUsername', 'user'),
                responder_username=data.get('responderUsername', 'GitHub Copilot'),
                messages=messages,
                file_path=str(file_path),
                file_size=file_path.stat().st_size,
                message_count=len(messages),
            )
            
        except Exception as e:
            print(f"⚠️ Error parsing {file_path.name}: {e}")
            return None
    
    def backup_all(self, project_filter: Optional[str] = None) -> Dict[str, Any]:
        """Perform full backup of all chat sessions."""
        print("🔄 Starting Copilot Chat Backup...")
        
        stats = {
            'total_workspaces': 0,
            'total_sessions': 0,
            'total_messages': 0,
            'total_size_bytes': 0,
            'projects': defaultdict(lambda: {'sessions': 0, 'messages': 0}),
            'backup_time': datetime.now().isoformat(),
        }
        
        all_sessions = []
        
        for ws_id, ws_info in self.workspace_map.items():
            project_name = ws_info['project_name']
            
            # Apply filter if specified
            if project_filter and project_filter.lower() not in project_name.lower():
                continue
                
            if not ws_info['chat_files']:
                continue
                
            stats['total_workspaces'] += 1
            
            for chat_file in ws_info['chat_files']:
                session = self._parse_chat_session(chat_file, ws_info)
                if session:
                    all_sessions.append(session)
                    stats['total_sessions'] += 1
                    stats['total_messages'] += session.message_count
                    stats['total_size_bytes'] += session.file_size
                    stats['projects'][project_name]['sessions'] += 1
                    stats['projects'][project_name]['messages'] += session.message_count
                    
                    # Backup raw file
                    self._backup_raw(chat_file, project_name)
        
        # Sort sessions by date
        all_sessions.sort(key=lambda s: s.last_message_date, reverse=True)
        
        # Generate outputs
        self._generate_markdown(all_sessions)
        self._generate_daily_summaries(all_sessions)
        self._generate_ai_export(all_sessions)
        self._generate_index(all_sessions, stats)
        
        # Convert defaultdict to regular dict for JSON serialization
        stats['projects'] = dict(stats['projects'])
        
        print(f"\n✅ Backup Complete!")
        print(f"   📁 Workspaces: {stats['total_workspaces']}")
        print(f"   💬 Sessions: {stats['total_sessions']}")
        print(f"   📝 Messages: {stats['total_messages']}")
        print(f"   💾 Size: {stats['total_size_bytes'] / (1024*1024):.2f} MB")
        print(f"   📂 Backup location: {self.backup_path}")
        
        return stats
    
    def _backup_raw(self, file_path: Path, project_name: str):
        """Backup raw JSON file with organization."""
        project_dir = self.raw_backup_path / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy with date prefix
        date_str = datetime.now().strftime("%Y-%m-%d")
        dest = project_dir / f"{date_str}_{file_path.name}"
        
        # Only copy if file has changed (compare hash)
        if dest.exists():
            existing_hash = hashlib.md5(dest.read_bytes()).hexdigest()
            new_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
            if existing_hash == new_hash:
                return
        
        shutil.copy2(file_path, dest)
    
    def _generate_markdown(self, sessions: List[ChatSession]):
        """Generate readable markdown files for each session."""
        for session in sessions:
            project_dir = self.markdown_path / session.workspace_name
            project_dir.mkdir(parents=True, exist_ok=True)
            
            date_str = session.creation_date.strftime("%Y-%m-%d_%H-%M")
            filename = f"{date_str}_{session.session_id[:8]}.md"
            filepath = project_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# Copilot Chat Session\n\n")
                f.write(f"**Project:** {session.workspace_name}\n")
                f.write(f"**Session ID:** {session.session_id}\n")
                f.write(f"**Created:** {session.creation_date.isoformat()}\n")
                f.write(f"**Last Message:** {session.last_message_date.isoformat()}\n")
                f.write(f"**Messages:** {session.message_count}\n")
                f.write(f"**Workspace:** `{session.workspace_path}`\n\n")
                f.write("---\n\n")
                
                for i, msg in enumerate(session.messages):
                    if msg.role == 'user':
                        f.write(f"## 👤 User\n\n")
                    else:
                        f.write(f"## 🤖 GitHub Copilot\n\n")
                    
                    # Clean and write content
                    content = msg.content.strip()
                    f.write(f"{content}\n\n")
                    f.write("---\n\n")
    
    def _generate_daily_summaries(self, sessions: List[ChatSession]):
        """Generate daily activity summaries."""
        # Group sessions by date
        by_date = defaultdict(list)
        for session in sessions:
            date_key = session.last_message_date.strftime("%Y-%m-%d")
            by_date[date_key].append(session)
        
        for date_str, day_sessions in by_date.items():
            filepath = self.daily_path / f"{date_str}.md"
            
            # Calculate stats
            total_messages = sum(s.message_count for s in day_sessions)
            projects = defaultdict(int)
            for s in day_sessions:
                projects[s.workspace_name] += s.message_count
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# Daily Copilot Activity - {date_str}\n\n")
                f.write(f"## Summary\n\n")
                f.write(f"- **Total Sessions:** {len(day_sessions)}\n")
                f.write(f"- **Total Messages:** {total_messages}\n")
                f.write(f"- **Projects Active:** {len(projects)}\n\n")
                
                f.write(f"## Projects\n\n")
                for project, msg_count in sorted(projects.items(), key=lambda x: -x[1]):
                    f.write(f"- **{project}:** {msg_count} messages\n")
                
                f.write(f"\n## Sessions\n\n")
                for session in sorted(day_sessions, key=lambda s: s.last_message_date, reverse=True):
                    time_str = session.last_message_date.strftime("%H:%M")
                    f.write(f"### {time_str} - {session.workspace_name}\n\n")
                    
                    # Show first user message as topic
                    for msg in session.messages:
                        if msg.role == 'user':
                            preview = msg.content[:200].replace('\n', ' ')
                            if len(msg.content) > 200:
                                preview += "..."
                            f.write(f"> {preview}\n\n")
                            break
                    
                    f.write(f"*{session.message_count} messages*\n\n")
    
    def _generate_ai_export(self, sessions: List[ChatSession]):
        """Generate AI-friendly export formats."""
        # Full JSON export
        export_data = {
            'export_date': datetime.now().isoformat(),
            'total_sessions': len(sessions),
            'sessions': []
        }
        
        for session in sessions:
            session_data = {
                'id': session.session_id,
                'project': session.workspace_name,
                'created': session.creation_date.isoformat(),
                'last_message': session.last_message_date.isoformat(),
                'message_count': session.message_count,
                'conversation': []
            }
            
            for msg in session.messages:
                session_data['conversation'].append({
                    'role': msg.role,
                    'content': msg.content,
                })
            
            export_data['sessions'].append(session_data)
        
        # Write full export
        with open(self.ai_export_path / "full_export.json", 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        # Write JSONL format (one session per line - good for training/analysis)
        with open(self.ai_export_path / "sessions.jsonl", 'w', encoding='utf-8') as f:
            for session_data in export_data['sessions']:
                f.write(json.dumps(session_data, ensure_ascii=False) + '\n')
        
        # Write conversations only (for embeddings/RAG)
        conversations = []
        for session in sessions:
            for i in range(0, len(session.messages), 2):
                if i + 1 < len(session.messages):
                    user_msg = session.messages[i]
                    assistant_msg = session.messages[i + 1]
                    if user_msg.role == 'user' and assistant_msg.role == 'assistant':
                        conversations.append({
                            'project': session.workspace_name,
                            'date': session.last_message_date.isoformat(),
                            'question': user_msg.content,
                            'answer': assistant_msg.content,
                        })
        
        with open(self.ai_export_path / "qa_pairs.json", 'w', encoding='utf-8') as f:
            json.dump(conversations, f, indent=2, ensure_ascii=False)
        
        with open(self.ai_export_path / "qa_pairs.jsonl", 'w', encoding='utf-8') as f:
            for qa in conversations:
                f.write(json.dumps(qa, ensure_ascii=False) + '\n')
        
        print(f"   📤 AI Export: {len(conversations)} Q&A pairs extracted")
    
    def _generate_index(self, sessions: List[ChatSession], stats: Dict):
        """Generate master index and search-friendly catalog."""
        index = {
            'generated': datetime.now().isoformat(),
            'stats': stats,
            'sessions': [],
            'by_project': defaultdict(list),
            'by_date': defaultdict(list),
        }
        
        for session in sessions:
            session_summary = {
                'id': session.session_id,
                'project': session.workspace_name,
                'created': session.creation_date.isoformat(),
                'last_message': session.last_message_date.isoformat(),
                'message_count': session.message_count,
                'file_size': session.file_size,
                'first_message_preview': '',
            }
            
            # Get first user message as preview
            for msg in session.messages:
                if msg.role == 'user':
                    session_summary['first_message_preview'] = msg.content[:300]
                    break
            
            index['sessions'].append(session_summary)
            index['by_project'][session.workspace_name].append(session_summary)
            
            date_key = session.last_message_date.strftime("%Y-%m-%d")
            index['by_date'][date_key].append(session_summary)
        
        # Convert defaultdicts
        index['by_project'] = dict(index['by_project'])
        index['by_date'] = dict(index['by_date'])
        
        with open(self.index_path / "master_index.json", 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        
        # Generate README
        with open(self.backup_path / "README.md", 'w', encoding='utf-8') as f:
            f.write("# Copilot Chat Backup\n\n")
            f.write(f"**Last Backup:** {datetime.now().isoformat()}\n\n")
            f.write("## Structure\n\n")
            f.write("```\n")
            f.write("copilot-chat-backups/\n")
            f.write("├── raw/              # Original JSON files by project\n")
            f.write("├── markdown/         # Human-readable markdown by project\n")
            f.write("├── daily/            # Daily activity summaries\n")
            f.write("├── ai-export/        # AI-friendly formats\n")
            f.write("│   ├── full_export.json    # Complete export\n")
            f.write("│   ├── sessions.jsonl      # One session per line\n")
            f.write("│   ├── qa_pairs.json       # Question-answer pairs\n")
            f.write("│   └── qa_pairs.jsonl      # Q&A pairs (JSONL)\n")
            f.write("├── index/            # Search indexes\n")
            f.write("│   └── master_index.json\n")
            f.write("└── README.md\n")
            f.write("```\n\n")
            
            f.write("## Statistics\n\n")
            f.write(f"- **Total Sessions:** {stats['total_sessions']}\n")
            f.write(f"- **Total Messages:** {stats['total_messages']}\n")
            f.write(f"- **Total Size:** {stats['total_size_bytes'] / (1024*1024):.2f} MB\n\n")
            
            f.write("## Projects\n\n")
            for project, data in sorted(stats['projects'].items()):
                f.write(f"- **{project}:** {data['sessions']} sessions, {data['messages']} messages\n")


def main():
    parser = argparse.ArgumentParser(description='Backup GitHub Copilot chat sessions')
    parser.add_argument('--backup-path', '-o', type=Path, 
                        help='Backup destination path')
    parser.add_argument('--workspace', '-w', type=str,
                        help='Filter by workspace/project name')
    parser.add_argument('--daily', action='store_true',
                        help='Generate daily summary only')
    parser.add_argument('--export-ai', action='store_true',
                        help='Generate AI export only')
    parser.add_argument('--list-workspaces', action='store_true',
                        help='List discovered workspaces and exit')
    
    args = parser.parse_args()
    
    backup = CopilotChatBackup(backup_path=args.backup_path)
    
    if args.list_workspaces:
        print("\n📂 Discovered Workspaces:\n")
        for ws_id, info in backup.workspace_map.items():
            if info['chat_count'] > 0:
                print(f"  {info['project_name']}")
                print(f"    ID: {ws_id}")
                print(f"    Path: {info['workspace_path']}")
                print(f"    Chats: {info['chat_count']}")
                print()
        return
    
    backup.backup_all(project_filter=args.workspace)


if __name__ == "__main__":
    main()
