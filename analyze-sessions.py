#!/usr/bin/env python3
"""
Analyze synced chat sessions and provide detailed breakdown.
Helps identify issues and track extraction progress.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
import json

def analyze_sessions(db_path="copilot_backup.db"):
    """Comprehensive session analysis."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 70)
    print("  COPILOT CHAT SESSIONS - COMPREHENSIVE ANALYSIS")
    print("=" * 70)
    
    # Overall stats
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN message_count = 0 THEN 1 END) as empty,
            COUNT(CASE WHEN message_count > 0 THEN 1 END) as with_messages,
            SUM(message_count) as total_messages,
            SUM(file_size) as total_size,
            MIN(datetime(creation_date)) as oldest,
            MAX(datetime(last_message_date)) as newest,
            COUNT(CASE WHEN session_type = 'conversation' THEN 1 END) as conversations,
            COUNT(CASE WHEN session_type = 'code_edit' THEN 1 END) as code_edits,
            COUNT(CASE WHEN session_type = 'mixed' THEN 1 END) as mixed,
            SUM(CASE WHEN session_type IN ('code_edit', 'mixed') THEN COALESCE(edit_line_count, 0) ELSE 0 END) as total_lines,
            SUM(CASE WHEN session_type IN ('code_edit', 'mixed') THEN COALESCE(edit_files_count, 0) ELSE 0 END) as total_files_edited
        FROM chat_sessions
    """)
    stats = dict(cursor.fetchone())
    
    print(f"\n📊 OVERALL STATISTICS")
    print(f"   Total Sessions: {stats['total']:,}")
    print(f"   With Messages: {stats['with_messages']:,} ({stats['with_messages']/stats['total']*100:.1f}%)")
    print(f"   Empty (0 msgs): {stats['empty']:,} ({stats['empty']/stats['total']*100:.1f}%)")
    print(f"   Total Messages: {stats['total_messages']:,}")
    print(f"   Total Size: {stats['total_size']/1024/1024:.2f} MB")
    print(f"   Date Range: {stats['oldest']} to {stats['newest']}")
    
    # Session type breakdown
    print(f"\n💬 SESSION TYPES")
    if stats['conversations'] or stats['code_edits'] or stats['mixed']:
        print(f"   Conversations: {stats['conversations']:,} ({stats['conversations']/stats['total']*100:.1f}%)")
        print(f"   Code Edits: {stats['code_edits']:,} ({stats['code_edits']/stats['total']*100:.1f}%)")
        if stats['mixed'] > 0:
            print(f"   Mixed: {stats['mixed']:,} ({stats['mixed']/stats['total']*100:.1f}%)")
        
        if stats['total_lines'] > 0:
            print(f"\n✏️  CODE EDIT STATISTICS")
            print(f"   Total Lines Edited: {stats['total_lines']:,}")
            print(f"   Total Files Edited: {stats['total_files_edited']:,}")
            avg_lines = stats['total_lines'] / max(stats['code_edits'] + stats['mixed'], 1)
            print(f"   Avg Lines/Edit Session: {avg_lines:.1f}")
    else:
        print(f"   (Session types not yet classified - run sync-with-edit-detection.py)")
    
    # Empty sessions by workspace
    print(f"\n⚠️  EMPTY SESSIONS BY WORKSPACE")
    cursor.execute("""
        SELECT workspace_name, COUNT(*) as count, GROUP_CONCAT(session_id, ', ') as session_ids
        FROM chat_sessions 
        WHERE message_count = 0
        GROUP BY workspace_name
        ORDER BY count DESC
        LIMIT 15
    """)
    print(f"{'Workspace':<35} {'Empty Sessions':<15}")
    print("-" * 70)
    for row in cursor:
        print(f"{row['workspace_name']:<35} {row['count']:<15}")
    
    # Active workspaces
    print(f"\n✅ TOP WORKSPACES BY ACTIVITY")
    cursor.execute("""
        SELECT 
            workspace_name,
            COUNT(*) as sessions,
            SUM(message_count) as messages,
            MAX(datetime(last_message_date)) as last_active
        FROM chat_sessions
        WHERE message_count > 0
        GROUP BY workspace_name
        ORDER BY messages DESC
        LIMIT 15
    """)
    print(f"{'Workspace':<35} {'Sessions':<12} {'Messages':<12} {'Last Active':<20}")
    print("-" * 70)
    for row in cursor:
        print(f"{row['workspace_name']:<35} {row['sessions']:<12} {row['messages']:<12} {row['last_active']:<20}")
    
    # Top edited files
    print(f"\n📝 TOP EDITED FILES (from code edit sessions)")
    cursor.execute("""
        SELECT edit_file_paths, COUNT(*) as edit_count
        FROM chat_sessions
        WHERE session_type IN ('code_edit', 'mixed') AND edit_file_paths IS NOT NULL AND edit_file_paths != ''
        GROUP BY edit_file_paths
        ORDER BY edit_count DESC
        LIMIT 10
    """)
    files_found = False
    for row in cursor:
        if not files_found:
            print(f"{'File Path':<70} {'Edits':<10}")
            print("-" * 70)
            files_found = True
        file_list = row['edit_file_paths'][:67] + "..." if len(row['edit_file_paths']) > 70 else row['edit_file_paths']
        print(f"{file_list:<70} {row['edit_count']:<10}")
    if not files_found:
        print("   (No code edit data available yet)")
    
    # Message distribution
    print(f"\n📈 MESSAGE COUNT DISTRIBUTION")
    cursor.execute("""
        SELECT 
            CASE 
                WHEN message_count = 0 THEN '0 (empty)'
                WHEN message_count BETWEEN 1 AND 5 THEN '1-5'
                WHEN message_count BETWEEN 6 AND 10 THEN '6-10'
                WHEN message_count BETWEEN 11 AND 20 THEN '11-20'
                WHEN message_count BETWEEN 21 AND 50 THEN '21-50'
                ELSE '50+'
            END as range,
            COUNT(*) as count
        FROM chat_sessions
        GROUP BY range
        ORDER BY MIN(message_count)
    """)
    for row in cursor:
        bar = '█' * int(row['count'] / stats['total'] * 50)
        print(f"   {row['range']:<12} {row['count']:>4} {bar}")
    
    # Sync history
    print(f"\n📅 SYNC HISTORY (Last 5 runs)")
    cursor.execute("""
        SELECT 
            datetime(started_at) as sync_time,
            total_sessions,
            inserted_sessions,
            updated_sessions,
            skipped_sessions,
            errors
        FROM chat_sync_runs
        ORDER BY id DESC
        LIMIT 5
    """)
    print(f"{'Sync Time':<20} {'Total':<8} {'New':<6} {'Updated':<9} {'Skipped':<9} {'Errors':<7}")
    print("-" * 70)
    for row in cursor:
        print(f"{row['sync_time']:<20} {row['total_sessions']:<8} {row['inserted_sessions']:<6} {row['updated_sessions']:<9} {row['skipped_sessions']:<9} {row['errors']:<7}")
    
    # Sample empty sessions
    print(f"\n🔍 SAMPLE EMPTY SESSIONS (checking file sizes)")
    cursor.execute("""
        SELECT session_id, workspace_name, file_size, file_path
        FROM chat_sessions
        WHERE message_count = 0
        ORDER BY file_size DESC
        LIMIT 10
    """)
    print(f"{'Session ID':<38} {'Workspace':<25} {'Size':<10}")
    print("-" * 70)
    for row in cursor:
        print(f"{row['session_id']:<38} {row['workspace_name']:<25} {row['file_size']:>6} bytes")
        # Check if file actually exists and has content
        file_path = Path(row['file_path'])
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    requests = content.get('requests', [])
                    print(f"   ↳ File has {len(requests)} requests but 0 extracted messages")
            except Exception as e:
                print(f"   ↳ Error reading file: {e}")
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS")
    if stats['empty'] > 0:
        print(f"   • {stats['empty']} sessions have 0 messages")
        print(f"     These may be:")
        print(f"       - Sessions created but never used")
        print(f"       - Files with parsing errors")
        print(f"       - Sessions with only system messages (no user/assistant exchanges)")
        print(f"     Run: python3 sync-chat-contents.py --retry-empty --verbose")
        print(f"          to attempt re-parsing these sessions")
    
    if stats['with_messages'] / stats['total'] > 0.9:
        print(f"   ✓ Excellent extraction rate: {stats['with_messages']/stats['total']*100:.1f}% of sessions have messages")
    
    print(f"\n{'=' * 70}")
    
    conn.close()


if __name__ == "__main__":
    analyze_sessions()
