#!/usr/bin/env python3
"""
Copilot Chat Search & Query Tool
=================================
Search and analyze backed up Copilot chat sessions.

Features:
- Full-text search across all conversations
- Filter by date, project, or topic
- Generate statistics and insights
- Export search results

Usage:
    python search-chats.py "error handling"              # Search all chats
    python search-chats.py "auth" --project aiconnects   # Search specific project
    python search-chats.py --today                       # Today's conversations
    python search-chats.py --stats                       # Show statistics
    python search-chats.py --topics                      # Extract common topics
"""

import json
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional

DEFAULT_BACKUP_PATH = Path.home() / "copilot-chat-backups"


class ChatSearcher:
    """Search and analyze Copilot chat backups."""
    
    def __init__(self, backup_path: Optional[Path] = None):
        self.backup_path = backup_path or DEFAULT_BACKUP_PATH
        self.index_file = self.backup_path / "index" / "master_index.json"
        self.ai_export_file = self.backup_path / "ai-export" / "full_export.json"
        
        self.index = self._load_index()
        self.sessions = self._load_sessions()
    
    def _load_index(self) -> Dict:
        """Load the master index."""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _load_sessions(self) -> List[Dict]:
        """Load all session data."""
        if self.ai_export_file.exists():
            with open(self.ai_export_file, 'r') as f:
                data = json.load(f)
                return data.get('sessions', [])
        return []
    
    def search(self, query: str, project: Optional[str] = None, 
               days: Optional[int] = None, limit: int = 20) -> List[Dict]:
        """Search conversations for a query string."""
        results = []
        query_lower = query.lower()
        
        cutoff_date = None
        if days:
            cutoff_date = datetime.now() - timedelta(days=days)
        
        for session in self.sessions:
            # Apply project filter
            if project and project.lower() not in session['project'].lower():
                continue
            
            # Apply date filter
            if cutoff_date:
                session_date = datetime.fromisoformat(session['last_message'])
                if session_date < cutoff_date:
                    continue
            
            # Search in conversation
            matches = []
            for msg in session.get('conversation', []):
                content = msg.get('content', '')
                if query_lower in content.lower():
                    # Extract context around match
                    match_pos = content.lower().find(query_lower)
                    start = max(0, match_pos - 100)
                    end = min(len(content), match_pos + len(query) + 100)
                    context = content[start:end]
                    if start > 0:
                        context = "..." + context
                    if end < len(content):
                        context = context + "..."
                    
                    matches.append({
                        'role': msg['role'],
                        'context': context,
                    })
            
            if matches:
                results.append({
                    'session_id': session['id'],
                    'project': session['project'],
                    'date': session['last_message'],
                    'match_count': len(matches),
                    'matches': matches[:3],  # Limit matches shown
                })
        
        # Sort by date (most recent first)
        results.sort(key=lambda x: x['date'], reverse=True)
        return results[:limit]
    
    def get_today(self) -> List[Dict]:
        """Get today's conversations."""
        today = datetime.now().strftime("%Y-%m-%d")
        results = []
        
        for session in self.sessions:
            session_date = session['last_message'][:10]
            if session_date == today:
                results.append(session)
        
        return results
    
    def get_stats(self) -> Dict:
        """Get overall statistics."""
        stats = {
            'total_sessions': len(self.sessions),
            'total_messages': 0,
            'total_qa_pairs': 0,
            'projects': defaultdict(lambda: {'sessions': 0, 'messages': 0}),
            'by_date': defaultdict(int),
            'avg_messages_per_session': 0,
        }
        
        for session in self.sessions:
            msg_count = session.get('message_count', len(session.get('conversation', [])))
            stats['total_messages'] += msg_count
            stats['total_qa_pairs'] += msg_count // 2
            
            project = session['project']
            stats['projects'][project]['sessions'] += 1
            stats['projects'][project]['messages'] += msg_count
            
            date = session['last_message'][:10]
            stats['by_date'][date] += 1
        
        if stats['total_sessions'] > 0:
            stats['avg_messages_per_session'] = stats['total_messages'] / stats['total_sessions']
        
        stats['projects'] = dict(stats['projects'])
        stats['by_date'] = dict(stats['by_date'])
        
        return stats
    
    def extract_topics(self, limit: int = 20) -> List[tuple]:
        """Extract common topics from user messages."""
        # Common words to filter out
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these',
            'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which',
            'who', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
            'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
            'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and',
            'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at',
            'by', 'for', 'with', 'about', 'against', 'between', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up',
            'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further',
            'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'any',
            'me', 'my', 'your', 'our', 'their', 'its', 'his', 'her', 'please',
            'help', 'want', 'need', 'like', 'make', 'create', 'add', 'get',
            'use', 'using', 'file', 'code', 'function', 'method', 'class',
        }
        
        word_counts = Counter()
        
        for session in self.sessions:
            for msg in session.get('conversation', []):
                if msg['role'] == 'user':
                    content = msg['content'].lower()
                    # Extract words (alphanumeric, 3+ chars)
                    words = re.findall(r'\b[a-z][a-z0-9_]{2,}\b', content)
                    for word in words:
                        if word not in stop_words:
                            word_counts[word] += 1
        
        return word_counts.most_common(limit)
    
    def get_project_summary(self, project: str) -> Dict:
        """Get summary for a specific project."""
        project_sessions = [s for s in self.sessions 
                          if project.lower() in s['project'].lower()]
        
        if not project_sessions:
            return {'error': f'No sessions found for project: {project}'}
        
        total_messages = sum(s.get('message_count', len(s.get('conversation', []))) 
                           for s in project_sessions)
        
        # Get date range
        dates = [s['last_message'][:10] for s in project_sessions]
        
        return {
            'project': project,
            'total_sessions': len(project_sessions),
            'total_messages': total_messages,
            'date_range': {
                'first': min(dates),
                'last': max(dates),
            },
            'recent_sessions': project_sessions[:5],
        }


def print_results(results: List[Dict], query: str):
    """Pretty print search results."""
    print(f"\n🔍 Search Results for: '{query}'")
    print("=" * 60)
    
    if not results:
        print("No matches found.")
        return
    
    print(f"Found {len(results)} sessions with matches\n")
    
    for r in results:
        print(f"📁 {r['project']} | {r['date'][:10]} | {r['match_count']} matches")
        for m in r['matches']:
            role_icon = "👤" if m['role'] == 'user' else "🤖"
            context = m['context'].replace('\n', ' ')[:150]
            print(f"   {role_icon} ...{context}...")
        print()


def print_stats(stats: Dict):
    """Pretty print statistics."""
    print("\n📊 Copilot Chat Statistics")
    print("=" * 60)
    print(f"Total Sessions:     {stats['total_sessions']}")
    print(f"Total Messages:     {stats['total_messages']}")
    print(f"Total Q&A Pairs:    {stats['total_qa_pairs']}")
    print(f"Avg Msgs/Session:   {stats['avg_messages_per_session']:.1f}")
    
    print("\n📁 By Project:")
    for project, data in sorted(stats['projects'].items(), 
                                 key=lambda x: -x[1]['sessions']):
        print(f"   {project}: {data['sessions']} sessions, {data['messages']} messages")
    
    print("\n📅 Recent Activity:")
    recent_dates = sorted(stats['by_date'].items(), reverse=True)[:7]
    for date, count in recent_dates:
        print(f"   {date}: {count} sessions")


def print_topics(topics: List[tuple]):
    """Pretty print extracted topics."""
    print("\n🏷️ Common Topics")
    print("=" * 60)
    
    max_count = topics[0][1] if topics else 1
    for word, count in topics:
        bar_len = int((count / max_count) * 30)
        bar = "█" * bar_len
        print(f"   {word:20s} {bar} ({count})")


def main():
    parser = argparse.ArgumentParser(description='Search Copilot chat backups')
    parser.add_argument('query', nargs='?', help='Search query')
    parser.add_argument('--project', '-p', help='Filter by project')
    parser.add_argument('--days', '-d', type=int, help='Search last N days only')
    parser.add_argument('--limit', '-n', type=int, default=20, help='Max results')
    parser.add_argument('--today', action='store_true', help='Show today\'s chats')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    parser.add_argument('--topics', action='store_true', help='Extract common topics')
    parser.add_argument('--backup-path', type=Path, help='Backup directory path')
    
    args = parser.parse_args()
    
    searcher = ChatSearcher(backup_path=args.backup_path)
    
    if not searcher.sessions:
        print("⚠️ No backup data found. Run backup-copilot-chats.py first.")
        return
    
    if args.stats:
        stats = searcher.get_stats()
        print_stats(stats)
    elif args.topics:
        topics = searcher.extract_topics()
        print_topics(topics)
    elif args.today:
        today_chats = searcher.get_today()
        print(f"\n📅 Today's Conversations ({len(today_chats)} sessions)")
        print("=" * 60)
        for s in today_chats:
            print(f"\n📁 {s['project']} | {s['message_count']} messages")
            # Show first user message
            for msg in s.get('conversation', []):
                if msg['role'] == 'user':
                    preview = msg['content'][:200].replace('\n', ' ')
                    print(f"   > {preview}...")
                    break
    elif args.query:
        results = searcher.search(
            args.query, 
            project=args.project,
            days=args.days,
            limit=args.limit
        )
        print_results(results, args.query)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
