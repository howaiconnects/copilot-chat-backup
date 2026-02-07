#!/usr/bin/env python3
"""
Copilot Chat Search API with Vector Database
=============================================
Provides semantic search capabilities for chat sessions using
Qdrant vector database and sentence transformers.

Features:
- Semantic search across all conversations
- Keyword filtering and faceted search
- Session-level and message-level search
- Real-time indexing of new content
- Prometheus metrics
"""

import os
import json
import time
import logging
import hashlib
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import re

# Third-party imports
try:
    from sentence_transformers import SentenceTransformer
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels
    from qdrant_client.http.exceptions import ResponseHandlingException
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('search-api')

# =============================================================================
# Constants
# =============================================================================

COLLECTION_NAME = "copilot_chats"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 dimension


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SearchResult:
    """A single search result."""
    session_id: str
    message_id: str
    project: str
    role: str
    content: str
    score: float
    created_at: str
    context: Optional[str] = None


@dataclass
class SearchMetrics:
    """Metrics for the search API."""
    total_searches: int = 0
    successful_searches: int = 0
    failed_searches: int = 0
    total_indexed_messages: int = 0
    total_indexed_sessions: int = 0
    avg_search_time_ms: float = 0
    last_index_time: Optional[str] = None


# =============================================================================
# Vector Search Engine
# =============================================================================

class VectorSearchEngine:
    """Manages vector embeddings and search in Qdrant."""
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ):
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.embedding_model_name = embedding_model
        
        # Initialize Qdrant client
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)
        
        # Initialize embedding model
        logger.info(f"Loading embedding model: {embedding_model}")
        self.model = SentenceTransformer(embedding_model)
        
        # Ensure collection exists
        self._ensure_collection()
        
        # Metrics
        self.metrics = SearchMetrics()
        self._metrics_lock = threading.Lock()
    
    def _ensure_collection(self):
        """Ensure the vector collection exists."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == COLLECTION_NAME for c in collections)
            
            if not exists:
                logger.info(f"Creating collection: {COLLECTION_NAME}")
                self.client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=qmodels.VectorParams(
                        size=EMBEDDING_DIM,
                        distance=qmodels.Distance.COSINE
                    )
                )
                
                # Create payload indexes for filtering
                self.client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="project",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
                self.client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="role",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
                self.client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="session_id",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
                
                logger.info("Collection created with indexes")
            else:
                logger.info(f"Collection {COLLECTION_NAME} already exists")
                
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
            raise
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    def index_sessions(self, sessions: List[Dict]) -> Tuple[int, int]:
        """Index chat sessions into the vector database."""
        logger.info(f"Indexing {len(sessions)} sessions...")
        start_time = time.time()
        
        points = []
        indexed_messages = 0
        
        for session in sessions:
            session_id = session.get('id', 'unknown')
            project = session.get('project', 'unknown')
            created = session.get('created', '')
            
            for i, msg in enumerate(session.get('conversation', [])):
                content = msg.get('content', '')
                if not content or len(content) < 10:
                    continue
                
                # Generate unique ID for this message
                msg_id = hashlib.md5(
                    f"{session_id}:{i}:{content[:100]}".encode()
                ).hexdigest()
                
                # Truncate content for embedding (max ~500 tokens)
                embed_text = content[:2000]
                
                try:
                    embedding = self.embed([embed_text])[0]
                    
                    points.append(qmodels.PointStruct(
                        id=msg_id,
                        vector=embedding,
                        payload={
                            'session_id': session_id,
                            'message_index': i,
                            'project': project,
                            'role': msg.get('role', 'unknown'),
                            'content': content[:1000],  # Store truncated for display
                            'full_content_hash': hashlib.md5(content.encode()).hexdigest(),
                            'created_at': created,
                            'indexed_at': datetime.now().isoformat(),
                        }
                    ))
                    indexed_messages += 1
                    
                except Exception as e:
                    logger.warning(f"Error embedding message: {e}")
                    continue
                
                # Batch upsert every 100 points
                if len(points) >= 100:
                    self._upsert_batch(points)
                    points = []
        
        # Upsert remaining points
        if points:
            self._upsert_batch(points)
        
        elapsed = time.time() - start_time
        logger.info(f"Indexed {indexed_messages} messages from {len(sessions)} sessions in {elapsed:.2f}s")
        
        with self._metrics_lock:
            self.metrics.total_indexed_messages = indexed_messages
            self.metrics.total_indexed_sessions = len(sessions)
            self.metrics.last_index_time = datetime.now().isoformat()
        
        return len(sessions), indexed_messages
    
    def _upsert_batch(self, points: List[qmodels.PointStruct]):
        """Upsert a batch of points."""
        try:
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
                wait=True
            )
        except Exception as e:
            logger.error(f"Error upserting batch: {e}")
    
    def search(
        self,
        query: str,
        limit: int = 10,
        project: Optional[str] = None,
        role: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """Perform semantic search."""
        start_time = time.time()
        
        try:
            # Generate query embedding
            query_embedding = self.embed([query])[0]
            
            # Build filter
            filter_conditions = []
            if project:
                filter_conditions.append(
                    qmodels.FieldCondition(
                        key="project",
                        match=qmodels.MatchValue(value=project)
                    )
                )
            if role:
                filter_conditions.append(
                    qmodels.FieldCondition(
                        key="role",
                        match=qmodels.MatchValue(value=role)
                    )
                )
            if session_id:
                filter_conditions.append(
                    qmodels.FieldCondition(
                        key="session_id",
                        match=qmodels.MatchValue(value=session_id)
                    )
                )
            
            query_filter = None
            if filter_conditions:
                query_filter = qmodels.Filter(must=filter_conditions)
            
            # Search
            results = self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            
            # Convert to SearchResult
            search_results = []
            for hit in results:
                payload = hit.payload or {}
                content = payload.get('content', '')
                
                # Extract context around query match
                context = self._extract_context(content, query)
                
                search_results.append(SearchResult(
                    session_id=payload.get('session_id', ''),
                    message_id=str(hit.id),
                    project=payload.get('project', ''),
                    role=payload.get('role', ''),
                    content=content,
                    score=hit.score,
                    created_at=payload.get('created_at', ''),
                    context=context,
                ))
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            with self._metrics_lock:
                self.metrics.total_searches += 1
                self.metrics.successful_searches += 1
                # Update rolling average
                n = self.metrics.successful_searches
                self.metrics.avg_search_time_ms = (
                    (self.metrics.avg_search_time_ms * (n - 1) + elapsed_ms) / n
                )
            
            return search_results
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            with self._metrics_lock:
                self.metrics.total_searches += 1
                self.metrics.failed_searches += 1
            raise
    
    def _extract_context(self, content: str, query: str, context_size: int = 150) -> str:
        """Extract context around query match."""
        query_lower = query.lower()
        content_lower = content.lower()
        
        pos = content_lower.find(query_lower)
        if pos == -1:
            # No exact match, return beginning
            return content[:context_size * 2] + ("..." if len(content) > context_size * 2 else "")
        
        start = max(0, pos - context_size)
        end = min(len(content), pos + len(query) + context_size)
        
        context = content[start:end]
        if start > 0:
            context = "..." + context
        if end < len(content):
            context = context + "..."
        
        return context
    
    def keyword_search(
        self,
        keywords: List[str],
        limit: int = 20,
        project: Optional[str] = None,
    ) -> List[Dict]:
        """Perform keyword-based search (scroll through collection)."""
        try:
            # Build filter with text match
            filter_conditions = []
            
            if project:
                filter_conditions.append(
                    qmodels.FieldCondition(
                        key="project",
                        match=qmodels.MatchValue(value=project)
                    )
                )
            
            # Scroll through collection and filter by keywords
            results = []
            offset = None
            
            while len(results) < limit:
                scroll_result = self.client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=qmodels.Filter(must=filter_conditions) if filter_conditions else None,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                )
                
                points, offset = scroll_result
                
                if not points:
                    break
                
                for point in points:
                    payload = point.payload or {}
                    content = payload.get('content', '').lower()
                    
                    # Check if all keywords are present
                    if all(kw.lower() in content for kw in keywords):
                        results.append({
                            'session_id': payload.get('session_id', ''),
                            'project': payload.get('project', ''),
                            'role': payload.get('role', ''),
                            'content': payload.get('content', ''),
                            'created_at': payload.get('created_at', ''),
                        })
                        
                        if len(results) >= limit:
                            break
                
                if offset is None:
                    break
            
            return results
            
        except Exception as e:
            logger.error(f"Keyword search error: {e}")
            raise
    
    def get_stats(self) -> Dict:
        """Get collection statistics."""
        try:
            info = self.client.get_collection(COLLECTION_NAME)
            return {
                'vectors_count': info.vectors_count,
                'indexed_vectors_count': info.indexed_vectors_count,
                'points_count': info.points_count,
                'status': info.status.value,
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'error': str(e)}
    
    def get_metrics(self) -> Dict:
        """Get search metrics."""
        with self._metrics_lock:
            return asdict(self.metrics)


# =============================================================================
# Search API Handler
# =============================================================================

class SearchAPIHandler(BaseHTTPRequestHandler):
    """HTTP handler for search API."""
    
    engine: VectorSearchEngine = None
    backup_path: Path = None
    
    def log_message(self, format, *args):
        logger.debug(f"HTTP: {args[0]}")
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        
        routes = {
            '/api/search': self._handle_search,
            '/api/keyword-search': self._handle_keyword_search,
            '/api/reindex': self._handle_reindex,
            '/api/stats': self._handle_stats,
            '/metrics': self._handle_metrics,
            '/health': self._handle_health,
            '/': self._handle_index,
        }
        
        handler = routes.get(path, self._handle_404)
        handler(query)
    
    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/search':
            # Read body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            try:
                data = json.loads(body)
                self._handle_search_post(data)
            except json.JSONDecodeError:
                self._send_error(400, "Invalid JSON")
        else:
            self._handle_404({})
    
    def _handle_search(self, query: Dict):
        """Handle semantic search."""
        q = query.get('q', [''])[0]
        if not q:
            self._send_error(400, "Query parameter 'q' is required")
            return
        
        limit = int(query.get('limit', ['10'])[0])
        project = query.get('project', [None])[0]
        role = query.get('role', [None])[0]
        
        try:
            results = self.engine.search(
                query=q,
                limit=limit,
                project=project,
                role=role,
            )
            
            self._send_json({
                'query': q,
                'results': [asdict(r) for r in results],
                'count': len(results),
            })
        except Exception as e:
            self._send_error(500, str(e))
    
    def _handle_search_post(self, data: Dict):
        """Handle POST search with full options."""
        q = data.get('query', '')
        if not q:
            self._send_error(400, "Query is required")
            return
        
        try:
            results = self.engine.search(
                query=q,
                limit=data.get('limit', 10),
                project=data.get('project'),
                role=data.get('role'),
                session_id=data.get('session_id'),
            )
            
            self._send_json({
                'query': q,
                'results': [asdict(r) for r in results],
                'count': len(results),
            })
        except Exception as e:
            self._send_error(500, str(e))
    
    def _handle_keyword_search(self, query: Dict):
        """Handle keyword-based search."""
        keywords = query.get('keywords', [''])[0]
        if not keywords:
            self._send_error(400, "Keywords parameter is required")
            return
        
        keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
        limit = int(query.get('limit', ['20'])[0])
        project = query.get('project', [None])[0]
        
        try:
            results = self.engine.keyword_search(
                keywords=keyword_list,
                limit=limit,
                project=project,
            )
            
            self._send_json({
                'keywords': keyword_list,
                'results': results,
                'count': len(results),
            })
        except Exception as e:
            self._send_error(500, str(e))
    
    def _handle_reindex(self, query: Dict):
        """Trigger reindexing of all sessions."""
        try:
            sessions = self._load_sessions()
            sessions_count, messages_count = self.engine.index_sessions(sessions)
            
            self._send_json({
                'status': 'success',
                'indexed_sessions': sessions_count,
                'indexed_messages': messages_count,
            })
        except Exception as e:
            self._send_error(500, str(e))
    
    def _handle_stats(self, query: Dict):
        """Get vector database statistics."""
        try:
            stats = self.engine.get_stats()
            metrics = self.engine.get_metrics()
            
            self._send_json({
                'database': stats,
                'api': metrics,
            })
        except Exception as e:
            self._send_error(500, str(e))
    
    def _handle_metrics(self, query: Dict):
        """Prometheus metrics endpoint."""
        metrics = self.engine.get_metrics()
        stats = self.engine.get_stats()
        
        lines = [
            "# HELP copilot_search_total Total search requests",
            "# TYPE copilot_search_total counter",
            f"copilot_search_total {metrics.get('total_searches', 0)}",
            "",
            "# HELP copilot_search_success_total Successful searches",
            "# TYPE copilot_search_success_total counter",
            f"copilot_search_success_total {metrics.get('successful_searches', 0)}",
            "",
            "# HELP copilot_search_errors_total Failed searches",
            "# TYPE copilot_search_errors_total counter",
            f"copilot_search_errors_total {metrics.get('failed_searches', 0)}",
            "",
            "# HELP copilot_search_latency_avg_ms Average search latency in milliseconds",
            "# TYPE copilot_search_latency_avg_ms gauge",
            f"copilot_search_latency_avg_ms {metrics.get('avg_search_time_ms', 0):.2f}",
            "",
            "# HELP copilot_indexed_messages_total Total indexed messages",
            "# TYPE copilot_indexed_messages_total gauge",
            f"copilot_indexed_messages_total {metrics.get('total_indexed_messages', 0)}",
            "",
            "# HELP copilot_indexed_sessions_total Total indexed sessions",
            "# TYPE copilot_indexed_sessions_total gauge",
            f"copilot_indexed_sessions_total {metrics.get('total_indexed_sessions', 0)}",
            "",
            "# HELP copilot_qdrant_vectors_count Total vectors in Qdrant",
            "# TYPE copilot_qdrant_vectors_count gauge",
            f"copilot_qdrant_vectors_count {stats.get('vectors_count', 0)}",
        ]
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write('\n'.join(lines).encode('utf-8'))
    
    def _handle_health(self, query: Dict):
        """Health check."""
        try:
            stats = self.engine.get_stats()
            healthy = stats.get('status') == 'green' or stats.get('status') == 'yellow'
            
            self.send_response(200 if healthy else 503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'healthy' if healthy else 'unhealthy',
                'qdrant_status': stats.get('status', 'unknown'),
            }).encode('utf-8'))
        except Exception as e:
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'unhealthy',
                'error': str(e),
            }).encode('utf-8'))
    
    def _handle_index(self, query: Dict):
        """Index page."""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Copilot Chat Search API</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        h1 { color: #333; }
        .endpoint { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .method { color: #fff; padding: 3px 8px; border-radius: 3px; font-size: 12px; }
        .get { background: #61affe; }
        .post { background: #49cc90; }
        code { background: #eee; padding: 2px 5px; border-radius: 3px; }
    </style>
</head>
<body>
    <h1>🔍 Copilot Chat Search API</h1>
    <p>Semantic search across all your Copilot chat sessions.</p>
    
    <div class="endpoint">
        <span class="method get">GET</span>
        <strong>/api/search</strong>
        <p>Semantic search. Params: <code>q</code> (required), <code>limit</code>, <code>project</code>, <code>role</code></p>
        <p>Example: <code>/api/search?q=error handling&limit=5&project=aiconnects-hub</code></p>
    </div>
    
    <div class="endpoint">
        <span class="method get">GET</span>
        <strong>/api/keyword-search</strong>
        <p>Keyword search. Params: <code>keywords</code> (comma-separated), <code>limit</code>, <code>project</code></p>
        <p>Example: <code>/api/keyword-search?keywords=python,async,await</code></p>
    </div>
    
    <div class="endpoint">
        <span class="method get">GET</span>
        <strong>/api/reindex</strong>
        <p>Trigger full reindex of all sessions.</p>
    </div>
    
    <div class="endpoint">
        <span class="method get">GET</span>
        <strong>/api/stats</strong>
        <p>Get database and API statistics.</p>
    </div>
    
    <div class="endpoint">
        <span class="method get">GET</span>
        <strong>/metrics</strong>
        <p>Prometheus metrics endpoint.</p>
    </div>
    
    <div class="endpoint">
        <span class="method get">GET</span>
        <strong>/health</strong>
        <p>Health check endpoint.</p>
    </div>
</body>
</html>"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def _handle_404(self, query: Dict):
        """404 handler."""
        self._send_error(404, "Not Found")
    
    def _load_sessions(self) -> List[Dict]:
        """Load sessions from backup."""
        export_path = self.backup_path / "ai-export" / "full_export.json"
        if export_path.exists():
            with open(export_path, 'r') as f:
                data = json.load(f)
                return data.get('sessions', [])
        return []
    
    def _send_json(self, data: Dict):
        """Send JSON response."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))
    
    def _send_error(self, code: int, message: str):
        """Send error response."""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}).encode('utf-8'))


# =============================================================================
# Main
# =============================================================================

def main():
    """Main entry point."""
    if not HAS_DEPENDENCIES:
        logger.error(f"Missing dependencies: {IMPORT_ERROR}")
        logger.error("Install with: pip install sentence-transformers qdrant-client")
        return
    
    backup_path = Path(os.environ.get('BACKUP_PATH', str(Path.home() / 'copilot-chat-backups')))
    qdrant_host = os.environ.get('QDRANT_HOST', 'localhost')
    qdrant_port = int(os.environ.get('QDRANT_PORT', '6333'))
    api_port = int(os.environ.get('API_PORT', '8081'))
    embedding_model = os.environ.get('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
    
    logger.info("Starting Copilot Chat Search API")
    logger.info(f"Backup path: {backup_path}")
    logger.info(f"Qdrant: {qdrant_host}:{qdrant_port}")
    logger.info(f"API port: {api_port}")
    
    # Wait for Qdrant to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            engine = VectorSearchEngine(
                qdrant_host=qdrant_host,
                qdrant_port=qdrant_port,
                embedding_model=embedding_model,
            )
            break
        except Exception as e:
            if i < max_retries - 1:
                logger.warning(f"Waiting for Qdrant... ({i+1}/{max_retries})")
                time.sleep(2)
            else:
                logger.error(f"Could not connect to Qdrant: {e}")
                raise
    
    # Initial indexing
    logger.info("Performing initial indexing...")
    export_path = backup_path / "ai-export" / "full_export.json"
    if export_path.exists():
        with open(export_path, 'r') as f:
            data = json.load(f)
            sessions = data.get('sessions', [])
            if sessions:
                engine.index_sessions(sessions)
    else:
        logger.warning(f"No export file found at {export_path}")
    
    # Set up handler
    SearchAPIHandler.engine = engine
    SearchAPIHandler.backup_path = backup_path
    
    # Start server
    server = HTTPServer(('0.0.0.0', api_port), SearchAPIHandler)
    logger.info(f"Search API running on http://0.0.0.0:{api_port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
