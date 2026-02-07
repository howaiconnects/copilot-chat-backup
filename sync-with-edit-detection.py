#!/usr/bin/env python3
"""
Enhanced Copilot Chat Sync with Code Edit Detection
====================================================
Syncs chat sessions and detects code generation vs conversations.
Extracts metadata from textEditGroup responses.

Usage:
    python3 sync-with-edit-detection.py
    python3 sync-with-edit-detection.py --storage-path /path/to/storage
    python3 sync-with-edit-detection.py --force-resync
"""

import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from db_manager import BackupDatabase

# Storage path discovery
POSSIBLE_STORAGE_PATHS = [
    Path("/mnt/c/Users/dimoss/AppData/Roaming/Code/User/workspaceStorage"),
    Path.home() / ".vscode-server/data/User/workspaceStorage",
    Path.home() / ".config/Code/User/workspaceStorage",
    Path.home() / "Library/Application Support/Code/User/workspaceStorage",
]

def find_storage_path() -> Optional[Path]:
    """Find VS Code storage path."""
    for path in POSSIBLE_STORAGE_PATHS:
        if path.exists():
            return path
    return None


def extract_edit_metadata(response: Any) -> Dict[str, Any]:
    """Extract metadata from textEditGroup responses."""
    metadata = {
        'edit_file_paths': [],
        'edit_line_count': 0,
        'edit_files_count': 0,
    }
    
    if not isinstance(response, list):
        response = [response]
    
    for resp_item in response:
        if not isinstance(resp_item, dict):
            continue
            
        kind = resp_item.get('kind', '')
        
        if kind == 'textEditGroup':
            # Extract file path
            uri_info = resp_item.get('uri', {})
            if isinstance(uri_info, dict):
                file_path = uri_info.get('fsPath') or uri_info.get('path', '')
                if file_path and file_path not in metadata['edit_file_paths']:
                    metadata['edit_file_paths'].append(file_path)
            
            # Count edits and lines
            edits = resp_item.get('edits', [])
            for edit_group in edits:
                if isinstance(edit_group, list):
                    for edit in edit_group:
                        if isinstance(edit, dict) and 'range' in edit:
                            range_info = edit['range']
                            start_line = range_info.get('startLineNumber', 0)
                            end_line = range_info.get('endLineNumber', 0)
                            metadata['edit_line_count'] += abs(end_line - start_line) + 1
    
    metadata['edit_files_count'] = len(metadata['edit_file_paths'])
    metadata['edit_file_paths'] = ', '.join(metadata['edit_file_paths'][:10])  # Limit to 10 files
    
    return metadata


def determine_session_type(requests: List[Dict]) -> Tuple[str, Dict[str, Any]]:
    """
    Determine session type and extract edit metadata.
    
    Returns:
        Tuple of (session_type, edit_metadata)
        session_type: 'conversation', 'code_edit', or 'mixed'
    """
    has_conversation = False
    has_code_edit = False
    all_edit_metadata = {
        'edit_file_paths': set(),
        'edit_line_count': 0,
        'edit_files_count': 0,
    }
    
    for req in requests:
        # Check user message
        user_msg = req.get('message', {})
        user_text = user_msg.get('text', '') if isinstance(user_msg, dict) else str(user_msg)
        
        if user_text and len(user_text.strip()) > 0:
            has_conversation = True
        
        # Check response type
        response = req.get('response', {})
        
        # Extract response content
        if isinstance(response, dict):
            # Check for textEditGroup
            kind = response.get('kind', '')
            if kind == 'textEditGroup':
                has_code_edit = True
                edit_meta = extract_edit_metadata(response)
                all_edit_metadata['edit_line_count'] += edit_meta['edit_line_count']
                if edit_meta['edit_file_paths']:
                    for path in edit_meta['edit_file_paths'].split(', '):
                        all_edit_metadata['edit_file_paths'].add(path)
            
            # Check for text response
            value = response.get('value', '') or response.get('result', {}).get('value', '')
            if value and len(str(value).strip()) > 0:
                has_conversation = True
        
        elif isinstance(response, list):
            for resp_item in response:
                if isinstance(resp_item, dict):
                    kind = resp_item.get('kind', '')
                    if kind == 'textEditGroup':
                        has_code_edit = True
                        edit_meta = extract_edit_metadata(resp_item)
                        all_edit_metadata['edit_line_count'] += edit_meta['edit_line_count']
                        if edit_meta['edit_file_paths']:
                            for path in edit_meta['edit_file_paths'].split(', '):
                                all_edit_metadata['edit_file_paths'].add(path)
    
    # Determine session type
    if has_code_edit and has_conversation:
        session_type = 'mixed'
    elif has_code_edit:
        session_type = 'code_edit'
    else:
        session_type = 'conversation'
    
    # Format edit metadata
    all_edit_metadata['edit_files_count'] = len(all_edit_metadata['edit_file_paths'])
    all_edit_metadata['edit_file_paths'] = ', '.join(list(all_edit_metadata['edit_file_paths'])[:10])
    
    return session_type, all_edit_metadata


def parse_session(file_path: Path) -> Optional[Dict[str, Any]]:
    """Parse a chat session file with edit detection."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        requests = data.get('requests', [])
        
        # Determine session type and extract edit metadata
        session_type, edit_metadata = determine_session_type(requests)
        
        # Extract conversational messages
        messages = []
        for req in requests:
            # User message
            user_msg = req.get('message', {})
            user_text = user_msg.get('text', '') if isinstance(user_msg, dict) else str(user_msg)
            
            if user_text:
                messages.append({
                    'role': 'user',
                    'content': user_text,
                    'position': len(messages),
                })
            
            # Assistant response (text only, not code edits)
            response = req.get('response', {})
            if isinstance(response, dict):
                resp_text = response.get('value', '') or response.get('result', {}).get('value', '')
                if resp_text:
                    messages.append({
                        'role': 'assistant',
                        'content': resp_text,
                        'position': len(messages),
                    })
        
        # Parse timestamps
        creation_ts = data.get('creationDate', 0)
        last_msg_ts = data.get('lastMessageDate', creation_ts)
        
        if creation_ts > 1e12:
            creation_ts /= 1000
        if last_msg_ts > 1e12:
            last_msg_ts /= 1000
        
        # Extract additional metadata
        initial_location = None
        if requests:
            first_req = requests[0]
            initial_location_data = first_req.get('initialLocation', {})
            if isinstance(initial_location_data, dict):
                initial_location = json.dumps(initial_location_data)
        
        return {
            'session_id': data.get('sessionId', file_path.stem),
            'creation_date': datetime.fromtimestamp(creation_ts).isoformat() if creation_ts else None,
            'last_message_date': datetime.fromtimestamp(last_msg_ts).isoformat() if last_msg_ts else None,
            'requester_username': data.get('requesterUsername', 'user'),
            'responder_username': data.get('responderUsername', 'GitHub Copilot'),
            'message_count': len(messages),
            'messages': messages,
            'file_path': str(file_path),
            'file_size': file_path.stat().st_size,
            'session_type': session_type,
            'edit_file_paths': edit_metadata['edit_file_paths'],
            'edit_line_count': edit_metadata['edit_line_count'],
            'edit_files_count': edit_metadata['edit_files_count'],
            'custom_title': data.get('customTitle'),
            'initial_location': initial_location,
        }
        
    except Exception as e:
        print(f"Error parsing {file_path.name}: {e}")
        return None


def discover_workspaces(storage_path: Path) -> Dict[str, Dict]:
    """Discover all workspaces with chat sessions."""
    workspaces = {}
    
    for ws_dir in storage_path.iterdir():
        if not ws_dir.is_dir():
            continue
        
        chat_sessions_dir = ws_dir / "chatSessions"
        if not chat_sessions_dir.exists():
            continue
        
        chat_files = list(chat_sessions_dir.glob("*.json"))
        if not chat_files:
            continue
        
        workspace_json = ws_dir / "workspace.json"
        ws_path = ""
        
        if workspace_json.exists():
            try:
                with open(workspace_json, 'r') as f:
                    ws_data = json.load(f)
                ws_path = ws_data.get('folder') or ws_data.get('workspace', '')
            except:
                pass
        
        workspaces[ws_dir.name] = {
            'workspace_id': ws_dir.name,
            'workspace_path': ws_path,
            'chat_files': chat_files,
        }
    
    return workspaces


def sync_chats(storage_path: Path, force_resync: bool = False, verbose: bool = False):
    """Sync all chat sessions to database with edit detection."""
    db = BackupDatabase("copilot_backup.db")
    
    print(f"🔍 Discovering workspaces in {storage_path}")
    workspaces = discover_workspaces(storage_path)
    
    total_files = sum(len(ws['chat_files']) for ws in workspaces.values())
    print(f"📁 Found {len(workspaces)} workspaces with {total_files} chat session files\n")
    
    if total_files == 0:
        print("No chat session files found.")
        return
    
    stats = {
        'started_at': datetime.now().isoformat(),
        'total_sessions': 0,
        'inserted_sessions': 0,
        'updated_sessions': 0,
        'skipped_sessions': 0,
        'errors': 0,
        'conversation_sessions': 0,
        'code_edit_sessions': 0,
        'mixed_sessions': 0,
    }
    
    for ws_name, ws_info in workspaces.items():
        for chat_file in ws_info['chat_files']:
            try:
                # Calculate file hash
                file_hash = hashlib.md5(chat_file.read_bytes()).hexdigest()
                
                # Check if already synced
                if not force_resync:
                    existing_hash = db.get_chat_session_hash(chat_file.stem)
                    if existing_hash == file_hash:
                        stats['skipped_sessions'] += 1
                        continue
                
                # Parse session
                session = parse_session(chat_file)
                if not session:
                    stats['errors'] += 1
                    continue
                
                # Add workspace info
                session['workspace_id'] = ws_info['workspace_id']
                session['workspace_name'] = ws_info['workspace_path'].split('/')[-1] if ws_info['workspace_path'] else ws_name
                session['workspace_path'] = ws_info['workspace_path']
                session['project_name'] = session['workspace_name']
                
                # Sync to database
                messages = session.pop('messages', [])
                status = db.upsert_chat_session(session, messages, file_hash)
                
                stats['total_sessions'] += 1
                if status == 'inserted':
                    stats['inserted_sessions'] += 1
                elif status == 'updated':
                    stats['updated_sessions'] += 1
                elif status == 'skipped':
                    stats['skipped_sessions'] += 1
                
                # Track by session type
                session_type = session.get('session_type', 'conversation')
                if session_type == 'conversation':
                    stats['conversation_sessions'] += 1
                elif session_type == 'code_edit':
                    stats['code_edit_sessions'] += 1
                elif session_type == 'mixed':
                    stats['mixed_sessions'] += 1
                
                if verbose:
                    print(f"  ✓ {status.upper()}: {session['session_id'][:8]}... ({session_type}, {session['message_count']} msgs)")
                
            except Exception as e:
                stats['errors'] += 1
                print(f"  ✗ Error processing {chat_file.name}: {e}")
    
    stats['finished_at'] = datetime.now().isoformat()
    
    # Save sync run stats
    db.record_chat_sync_run(stats)
    db.close()
    
    # Print summary
    print("\n" + "="*60)
    print("✅ Sync Complete!")
    print(f"   Total Sessions: {stats['total_sessions']}")
    print(f"   Inserted: {stats['inserted_sessions']}")
    print(f"   Updated: {stats['updated_sessions']}")
    print(f"   Skipped: {stats['skipped_sessions']}")
    print(f"   Errors: {stats['errors']}")
    print(f"\n📊 Session Types:")
    print(f"   Conversations: {stats['conversation_sessions']} ({stats['conversation_sessions']/max(stats['total_sessions'],1)*100:.1f}%)")
    print(f"   Code Edits: {stats['code_edit_sessions']} ({stats['code_edit_sessions']/max(stats['total_sessions'],1)*100:.1f}%)")
    print(f"   Mixed: {stats['mixed_sessions']} ({stats['mixed_sessions']/max(stats['total_sessions'],1)*100:.1f}%)")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(description='Sync Copilot chats with edit detection')
    parser.add_argument('--storage-path', type=Path, help='VS Code storage path')
    parser.add_argument('--force-resync', action='store_true', help='Force resync all sessions')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Find storage path
    storage_path = args.storage_path or find_storage_path()
    
    if not storage_path or not storage_path.exists():
        print("❌ Could not find VS Code storage path")
        print("\nTried:")
        for path in POSSIBLE_STORAGE_PATHS:
            print(f"  - {path}")
        print("\nSpecify path with: --storage-path /path/to/workspaceStorage")
        return 1
    
    sync_chats(storage_path, force_resync=args.force_resync, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    exit(main())
