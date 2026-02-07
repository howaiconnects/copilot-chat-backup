#!/usr/bin/env python3
"""
Update Session Types and Edit Metadata
=======================================
Re-parses existing sessions to populate session_type and edit metadata columns.

Usage:
    python3 update-session-types.py
    python3 update-session-types.py --limit 100
"""

import json
import argparse
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

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


def update_session_types(limit: Optional[int] = None, verbose: bool = True):
    """Update session types and edit metadata for all sessions."""
    conn = sqlite3.connect("copilot_backup.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all sessions
    if limit:
        cursor.execute("SELECT session_id, file_path FROM chat_sessions LIMIT ?", (limit,))
    else:
        cursor.execute("SELECT session_id, file_path FROM chat_sessions")
    
    sessions = cursor.fetchall()
    total = len(sessions)
    
    print(f"🔄 Updating session types for {total} sessions...\n")
    
    stats = {
        'processed': 0,
        'conversation': 0,
        'code_edit': 0,
        'mixed': 0,
        'errors': 0,
        'total_lines': 0,
        'total_files': 0,
    }
    
    for i, row in enumerate(sessions, 1):
        session_id = row['session_id']
        file_path = Path(row['file_path'])
        
        if not file_path.exists():
            if verbose:
                print(f"  ✗ File not found: {session_id[:8]}...")
            stats['errors'] += 1
            continue
        
        try:
            # Parse file
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            requests = data.get('requests', [])
            
            # Determine session type
            session_type, edit_metadata = determine_session_type(requests)
            
            # Update database
            cursor.execute("""
                UPDATE chat_sessions 
                SET session_type = ?,
                    edit_file_paths = ?,
                    edit_line_count = ?,
                    edit_files_count = ?
                WHERE session_id = ?
            """, (
                session_type,
                edit_metadata['edit_file_paths'],
                edit_metadata['edit_line_count'],
                edit_metadata['edit_files_count'],
                session_id
            ))
            
            stats['processed'] += 1
            stats[session_type] += 1
            stats['total_lines'] += edit_metadata['edit_line_count']
            stats['total_files'] += edit_metadata['edit_files_count']
            
            if verbose and i % 50 == 0:
                print(f"  Progress: {i}/{total} ({i/total*100:.1f}%) - "
                      f"Conv: {stats['conversation']}, Code: {stats['code_edit']}, Mixed: {stats['mixed']}")
            
        except Exception as e:
            if verbose:
                print(f"  ✗ Error processing {session_id[:8]}...: {e}")
            stats['errors'] += 1
    
    conn.commit()
    conn.close()
    
    # Print summary
    print("\n" + "="*60)
    print("✅ Update Complete!")
    print(f"   Processed: {stats['processed']}/{total}")
    print(f"   Conversations: {stats['conversation']} ({stats['conversation']/stats['processed']*100:.1f}%)")
    print(f"   Code Edits: {stats['code_edit']} ({stats['code_edit']/stats['processed']*100:.1f}%)")
    print(f"   Mixed: {stats['mixed']} ({stats['mixed']/stats['processed']*100:.1f}%)")
    print(f"   Errors: {stats['errors']}")
    print(f"\n✏️  Edit Statistics:")
    print(f"   Total Lines Edited: {stats['total_lines']:,}")
    print(f"   Total Files Edited: {stats['total_files']:,}")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(description='Update session types and edit metadata')
    parser.add_argument('--limit', type=int, help='Limit number of sessions to update')
    parser.add_argument('--verbose', '-v', action='store_true', default=True, help='Verbose output')
    parser.add_argument('--quiet', '-q', action='store_true', help='Quiet mode (only show summary)')
    
    args = parser.parse_args()
    
    update_session_types(limit=args.limit, verbose=not args.quiet)


if __name__ == "__main__":
    main()
