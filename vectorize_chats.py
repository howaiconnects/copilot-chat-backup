#!/usr/bin/env python3
"""
Vectorize Copilot Chat conversations and store in Qdrant
Supports Azure OpenAI (via AI Foundry), OpenAI, and local embeddings
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)

# Import for embeddings (install: pip install openai)
try:
    from openai import AzureOpenAI, OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    print("⚠️  OpenAI library not found. Install: pip install openai")

class ChatVectorizer:
    """Vectorize and sync chat conversations to Qdrant"""
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6337,
        collection_name: str = "copilot_chats",
        embedding_provider: str = "azure",  # azure, openai, or local
        azure_endpoint: Optional[str] = None,
        azure_api_key: Optional[str] = None,
        azure_deployment: str = "text-embedding-3-small",
        openai_api_key: Optional[str] = None,
        db_path: str = "./copilot_backup.db"
    ):
        """
        Initialize vectorizer with Qdrant and embedding provider
        
        Args:
            qdrant_host: Qdrant server host (default: localhost)
            qdrant_port: Qdrant server port (default: 6337)
            collection_name: Qdrant collection name
            embedding_provider: 'azure' (AI Foundry), 'openai', or 'local'
            azure_endpoint: Azure OpenAI endpoint (e.g., https://your-resource.openai.azure.com/)
            azure_api_key: Azure OpenAI API key (or set AZURE_OPENAI_API_KEY env var)
            azure_deployment: Azure deployment name (default: text-embedding-3-small)
            openai_api_key: OpenAI API key (or set OPENAI_API_KEY env var)
            db_path: Path to SQLite database
        """
        # Initialize Qdrant client
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.collection_name = collection_name
        self.db_path = db_path
        self.embedding_provider = embedding_provider
        
        # Initialize embedding client
        if embedding_provider == "azure":
            if not HAS_OPENAI:
                raise ImportError("Install openai library: pip install openai")
            
            api_key = azure_api_key or os.getenv("AZURE_OPENAI_API_KEY")
            endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
            
            if not api_key or not endpoint:
                raise ValueError(
                    "Azure OpenAI requires AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT\n"
                    "Set via environment variables or pass to constructor"
                )
            
            self.embedding_client = AzureOpenAI(
                api_key=api_key,
                api_version="2024-02-01",
                azure_endpoint=endpoint
            )
            self.embedding_model = azure_deployment
            self.vector_size = 1536  # text-embedding-3-small
            
        elif embedding_provider == "openai":
            if not HAS_OPENAI:
                raise ImportError("Install openai library: pip install openai")
            
            api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI requires OPENAI_API_KEY")
            
            self.embedding_client = OpenAI(api_key=api_key)
            self.embedding_model = "text-embedding-3-small"
            self.vector_size = 1536
            
        else:
            raise ValueError(f"Unsupported embedding provider: {embedding_provider}")
        
        # Create collection if it doesn't exist
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Create Qdrant collection if it doesn't exist"""
        collections = self.qdrant.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            print(f"📦 Creating collection '{self.collection_name}'...")
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE
                )
            )
            print(f"✅ Collection created with vector size {self.vector_size}")
        else:
            print(f"✅ Using existing collection '{self.collection_name}'")
    
    def get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using configured provider"""
        response = self.embedding_client.embeddings.create(
            input=text,
            model=self.embedding_model
        )
        return response.data[0].embedding
    
    def load_chats_from_db(self, workspace: Optional[str] = None) -> List[Dict]:
        """Load chat sessions from SQLite database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if workspace:
            cursor.execute("""
                SELECT s.session_id, s.workspace, s.title, s.start_time, s.end_time,
                       s.message_count, s.total_tokens, s.file_path,
                       GROUP_CONCAT(m.content, '\n---\n') as full_conversation
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                WHERE s.workspace = ?
                GROUP BY s.session_id
                ORDER BY s.start_time DESC
            """, (workspace,))
        else:
            cursor.execute("""
                SELECT s.session_id, s.workspace, s.title, s.start_time, s.end_time,
                       s.message_count, s.total_tokens, s.file_path,
                       GROUP_CONCAT(m.content, '\n---\n') as full_conversation
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                GROUP BY s.session_id
                ORDER BY s.start_time DESC
            """)
        
        chats = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return chats
    
    def vectorize_chat(self, chat: Dict) -> PointStruct:
        """Convert a chat session to a Qdrant point with embedding"""
        # Create searchable text (title + conversation excerpt)
        title = chat.get('title', 'Untitled')
        conversation = chat.get('full_conversation', '')
        
        # Truncate conversation for embedding (first 8000 chars)
        conversation_excerpt = conversation[:8000] if conversation else ""
        
        # Combine for embedding
        search_text = f"{title}\n\n{conversation_excerpt}"
        
        # Generate embedding
        vector = self.get_embedding(search_text)
        
        # Create payload with all metadata
        payload = {
            'session_id': chat['session_id'],
            'workspace': chat['workspace'],
            'title': title,
            'start_time': chat.get('start_time', ''),
            'end_time': chat.get('end_time', ''),
            'message_count': chat.get('message_count', 0),
            'total_tokens': chat.get('total_tokens', 0),
            'file_path': chat.get('file_path', ''),
            'full_conversation': conversation,
            'indexed_at': datetime.utcnow().isoformat()
        }
        
        # Use session_id as the point ID (hash to int)
        point_id = hash(chat['session_id']) & 0x7FFFFFFF
        
        return PointStruct(
            id=point_id,
            vector=vector,
            payload=payload
        )
    
    def sync_to_qdrant(self, workspace: Optional[str] = None, batch_size: int = 10):
        """
        Sync all chats from SQLite to Qdrant
        
        Args:
            workspace: Optional workspace filter
            batch_size: Number of chats to process in each batch
        """
        print(f"🔄 Loading chats from database...")
        chats = self.load_chats_from_db(workspace)
        
        if not chats:
            print("⚠️  No chats found in database")
            return
        
        print(f"📊 Found {len(chats)} chat sessions")
        print(f"🔮 Generating embeddings using {self.embedding_provider}...")
        
        # Process in batches
        points = []
        for i, chat in enumerate(chats, 1):
            try:
                point = self.vectorize_chat(chat)
                points.append(point)
                
                # Upload batch
                if len(points) >= batch_size:
                    self.qdrant.upsert(
                        collection_name=self.collection_name,
                        points=points
                    )
                    print(f"  ✅ Uploaded batch {i//batch_size} ({len(points)} chats)")
                    points = []
                    
            except Exception as e:
                print(f"  ❌ Failed to vectorize chat {chat.get('session_id', 'unknown')}: {e}")
        
        # Upload remaining points
        if points:
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=points
            )
            print(f"  ✅ Uploaded final batch ({len(points)} chats)")
        
        print(f"✅ Sync complete! {len(chats)} chats indexed in Qdrant")
    
    def search(
        self,
        query: str,
        workspace: Optional[str] = None,
        limit: int = 5,
        score_threshold: float = 0.7
    ) -> List[Dict]:
        """
        Semantic search for chat conversations
        
        Args:
            query: Search query (natural language)
            workspace: Optional workspace filter
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
        
        Returns:
            List of matching chat sessions with scores
        """
        # Generate query embedding
        query_vector = self.get_embedding(query)
        
        # Build filter
        query_filter = None
        if workspace:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="workspace",
                        match=MatchValue(value=workspace)
                    )
                ]
            )
        
        # Search
        results = self.qdrant.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True
        )
        
        # Format results
        formatted = []
        for result in results:
            formatted.append({
                'score': result.score,
                'session_id': result.payload.get('session_id'),
                'workspace': result.payload.get('workspace'),
                'title': result.payload.get('title'),
                'start_time': result.payload.get('start_time'),
                'message_count': result.payload.get('message_count'),
                'file_path': result.payload.get('file_path'),
                'conversation': result.payload.get('full_conversation', '')[:500] + '...'
            })
        
        return formatted
    
    def get_collection_info(self) -> Dict:
        """Get information about the Qdrant collection"""
        info = self.qdrant.get_collection(self.collection_name)
        return {
            'name': info.name,
            'vectors_count': info.vectors_count,
            'points_count': info.points_count,
            'status': info.status,
            'vector_size': info.config.params.vectors.size,
            'distance': info.config.params.vectors.distance
        }


def main():
    """CLI interface for chat vectorization"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Vectorize Copilot chats and sync to Qdrant"
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Sync chats from SQLite to Qdrant'
    )
    parser.add_argument(
        '--search',
        type=str,
        help='Search query (semantic search)'
    )
    parser.add_argument(
        '--workspace',
        type=str,
        help='Filter by workspace name'
    )
    parser.add_argument(
        '--provider',
        choices=['azure', 'openai'],
        default='azure',
        help='Embedding provider (default: azure for AI Foundry)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=5,
        help='Maximum search results (default: 5)'
    )
    parser.add_argument(
        '--info',
        action='store_true',
        help='Show collection info'
    )
    
    args = parser.parse_args()
    
    # Initialize vectorizer
    try:
        vectorizer = ChatVectorizer(
            embedding_provider=args.provider,
            qdrant_host=os.getenv('QDRANT_HOST', 'localhost'),
            qdrant_port=int(os.getenv('QDRANT_PORT', '6337'))
        )
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        print("\n💡 Setup instructions:")
        print("   1. Start Qdrant: cd monitoring && docker-compose up -d qdrant")
        print("   2. Set environment variables:")
        print("      export AZURE_OPENAI_API_KEY='your-key'")
        print("      export AZURE_OPENAI_ENDPOINT='https://your-resource.openai.azure.com/'")
        print("   3. Install dependencies: pip install openai qdrant-client")
        return 1
    
    # Execute command
    if args.sync:
        vectorizer.sync_to_qdrant(workspace=args.workspace)
    
    elif args.search:
        print(f"🔍 Searching: '{args.search}'")
        if args.workspace:
            print(f"   Workspace: {args.workspace}")
        
        results = vectorizer.search(
            query=args.search,
            workspace=args.workspace,
            limit=args.limit
        )
        
        if not results:
            print("❌ No results found")
        else:
            print(f"\n✅ Found {len(results)} results:\n")
            for i, result in enumerate(results, 1):
                print(f"{i}. [{result['score']:.3f}] {result['title']}")
                print(f"   Workspace: {result['workspace']}")
                print(f"   Session: {result['session_id']}")
                print(f"   Time: {result['start_time']}")
                print(f"   Messages: {result['message_count']}")
                print(f"   File: {result['file_path']}")
                print()
    
    elif args.info:
        info = vectorizer.get_collection_info()
        print("📊 Collection Info:")
        for key, value in info.items():
            print(f"   {key}: {value}")
    
    else:
        parser.print_help()
    
    return 0


if __name__ == "__main__":
    exit(main())
