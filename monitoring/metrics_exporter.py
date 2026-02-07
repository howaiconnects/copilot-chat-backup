#!/usr/bin/env python3
"""
Copilot Chat Backup - Advanced Metrics Exporter
================================================
Exports comprehensive metrics for Prometheus about chat sessions,
messages, workspaces, and backup health.

Features:
- Per-workspace/project metrics
- Session duration and message count histograms
- Temporal analysis (hourly, daily patterns)
- Backup health monitoring
- API for JSON metric access
- Local SQLite database storage
"""

import os
import sys
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import yaml

# Add parent directory to path for db_manager import
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from db_manager import BackupDatabase
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    logging.warning("db_manager not available, database features disabled")

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('metrics-exporter')

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SessionMetrics:
    """Metrics for a single chat session."""
    session_id: str
    workspace: str
    project: str
    message_count: int
    user_messages: int
    assistant_messages: int
    created_at: datetime
    last_message_at: datetime
    duration_seconds: float
    file_size_bytes: int
    models_used: List[str] = field(default_factory=list)


@dataclass
class WorkspaceMetrics:
    """Aggregated metrics for a workspace."""
    workspace_id: str
    project_name: str
    session_count: int
    total_messages: int
    total_size_bytes: int
    first_session: datetime
    last_session: datetime
    avg_messages_per_session: float
    active_days: int


@dataclass
class BackupHealth:
    """Health status of the backup system."""
    last_backup_time: datetime
    backup_age_seconds: float
    total_size_bytes: int
    total_sessions: int
    total_messages: int
    workspaces: int
    is_healthy: bool
    error_count: int = 0


# =============================================================================
# Metrics Collector
# =============================================================================

class MetricsCollector:
    """Collects and aggregates metrics from backup data."""
    
    def __init__(self, backup_path: str, config_path: Optional[str] = None):
        self.backup_path = Path(backup_path)
        self.config = self._load_config(config_path)
        self._cache: Dict[str, Any] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = 60  # seconds
        self._lock = threading.Lock()
        
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from YAML file."""
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        return {
            'scan_interval_seconds': 60,
            'metrics': {'sessions': {'enabled': True}, 'messages': {'enabled': True}}
        }
    
    def collect(self) -> Dict[str, Any]:
        """Collect all metrics, using cache if valid."""
        with self._lock:
            now = time.time()
            if self._cache and (now - self._cache_time) < self._cache_ttl:
                return self._cache
            
            metrics = self._collect_fresh()
            self._cache = metrics
            self._cache_time = now
            return metrics
    
    def _collect_fresh(self) -> Dict[str, Any]:
        """Collect fresh metrics from backup data."""
        logger.info("Collecting fresh metrics...")
        start_time = time.time()
        
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'health': {},
            'sessions': [],
            'workspaces': {},
            'temporal': {},
            'totals': {},
        }
        
        try:
            # Load AI export data if available
            ai_export_path = self.backup_path / "ai-export" / "full_export.json"
            sessions_data = []
            
            if ai_export_path.exists():
                with open(ai_export_path, 'r') as f:
                    export = json.load(f)
                    sessions_data = export.get('sessions', [])
            
            # Process sessions
            session_metrics = []
            workspace_stats = defaultdict(lambda: {
                'sessions': 0, 'messages': 0, 'size': 0, 
                'first': None, 'last': None, 'days': set()
            })
            
            temporal_hourly = defaultdict(int)
            temporal_daily = defaultdict(int)
            temporal_weekly = defaultdict(int)
            
            total_messages = 0
            total_user_messages = 0
            total_assistant_messages = 0
            models_used = defaultdict(int)
            
            for session in sessions_data:
                # Parse session data
                session_id = session.get('id', 'unknown')
                project = session.get('project', 'unknown')
                conversation = session.get('conversation', [])
                
                user_msgs = sum(1 for m in conversation if m.get('role') == 'user')
                assistant_msgs = sum(1 for m in conversation if m.get('role') == 'assistant')
                msg_count = len(conversation)
                
                # Parse timestamps
                created_str = session.get('created', '')
                last_msg_str = session.get('last_message', '')
                
                try:
                    created_at = datetime.fromisoformat(created_str) if created_str else datetime.now()
                    last_message_at = datetime.fromisoformat(last_msg_str) if last_msg_str else created_at
                except:
                    created_at = datetime.now()
                    last_message_at = created_at
                
                duration = (last_message_at - created_at).total_seconds()
                
                # Track models used
                for msg in conversation:
                    if msg.get('model'):
                        models_used[msg['model']] += 1
                
                # Update workspace stats
                ws = workspace_stats[project]
                ws['sessions'] += 1
                ws['messages'] += msg_count
                ws['days'].add(created_at.date())
                
                if ws['first'] is None or created_at < ws['first']:
                    ws['first'] = created_at
                if ws['last'] is None or last_message_at > ws['last']:
                    ws['last'] = last_message_at
                
                # Temporal metrics
                hour_key = created_at.strftime('%H')
                day_key = created_at.strftime('%Y-%m-%d')
                week_key = created_at.strftime('%Y-W%W')
                
                temporal_hourly[hour_key] += 1
                temporal_daily[day_key] += msg_count
                temporal_weekly[week_key] += msg_count
                
                # Totals
                total_messages += msg_count
                total_user_messages += user_msgs
                total_assistant_messages += assistant_msgs
                
                session_metrics.append({
                    'session_id': session_id,
                    'project': project,
                    'message_count': msg_count,
                    'user_messages': user_msgs,
                    'assistant_messages': assistant_msgs,
                    'duration_seconds': duration,
                    'created_at': created_at.isoformat(),
                    'last_message_at': last_message_at.isoformat(),
                })
            
            # Calculate totals from directory if no export
            if not sessions_data:
                total_sessions, total_messages, total_size = self._scan_backup_directory()
            else:
                total_sessions = len(sessions_data)
                total_size = sum(
                    f.stat().st_size 
                    for f in self.backup_path.rglob('*') 
                    if f.is_file()
                ) if self.backup_path.exists() else 0
            
            # Build workspace metrics
            workspace_metrics = {}
            for project, stats in workspace_stats.items():
                workspace_metrics[project] = {
                    'session_count': stats['sessions'],
                    'total_messages': stats['messages'],
                    'avg_messages_per_session': stats['messages'] / max(stats['sessions'], 1),
                    'active_days': len(stats['days']),
                    'first_session': stats['first'].isoformat() if stats['first'] else None,
                    'last_session': stats['last'].isoformat() if stats['last'] else None,
                }
            
            # Health check
            health = self._check_health(total_sessions, total_messages, total_size, len(workspace_stats))
            
            # Compile final metrics
            metrics['health'] = health
            metrics['sessions'] = session_metrics
            metrics['workspaces'] = workspace_metrics
            metrics['temporal'] = {
                'hourly': dict(temporal_hourly),
                'daily': dict(temporal_daily),
                'weekly': dict(temporal_weekly),
            }
            metrics['totals'] = {
                'sessions': total_sessions,
                'messages': total_messages,
                'user_messages': total_user_messages,
                'assistant_messages': total_assistant_messages,
                'size_bytes': total_size,
                'workspaces': len(workspace_stats),
                'models': dict(models_used),
            }
            
            collection_time = time.time() - start_time
            metrics['collection_time_seconds'] = collection_time
            logger.info(f"Metrics collected in {collection_time:.2f}s")
            
            # Save to local database
            if DB_AVAILABLE:
                try:
                    db_path = self.backup_path.parent / 'copilot_backup.db'
                    db = BackupDatabase(str(db_path))
                    backup_run_id = db.save_backup_run(metrics)
                    db.close()
                    logger.info(f"Saved to database as backup run #{backup_run_id}")
                except Exception as db_error:
                    logger.warning(f"Failed to save to database: {db_error}")
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            metrics['error'] = str(e)
        
        return metrics
    
    def _scan_backup_directory(self) -> tuple:
        """Scan backup directory for basic stats."""
        total_sessions = 0
        total_messages = 0
        total_size = 0
        
        if not self.backup_path.exists():
            return total_sessions, total_messages, total_size
        
        # Count markdown files in sessions directories
        for ws_dir in self.backup_path.iterdir():
            if ws_dir.is_dir():
                sessions_dir = ws_dir / "sessions"
                if sessions_dir.exists():
                    session_files = list(sessions_dir.glob("*.md"))
                    total_sessions += len(session_files)
                    total_messages += len(session_files) * 8  # Rough estimate
        
        # Total size
        total_size = sum(
            f.stat().st_size 
            for f in self.backup_path.rglob('*') 
            if f.is_file()
        )
        
        return total_sessions, total_messages, total_size
    
    def _check_health(self, sessions: int, messages: int, size: int, workspaces: int) -> Dict:
        """Check backup health status."""
        index_path = self.backup_path / "index" / "master_index.json"
        
        last_backup = datetime.now()
        if index_path.exists():
            last_backup = datetime.fromtimestamp(index_path.stat().st_mtime)
        
        age_seconds = (datetime.now() - last_backup).total_seconds()
        is_healthy = age_seconds < 86400  # Less than 24 hours old
        
        return {
            'last_backup_time': last_backup.isoformat(),
            'backup_age_seconds': age_seconds,
            'is_healthy': is_healthy,
            'total_sessions': sessions,
            'total_messages': messages,
            'total_size_bytes': size,
            'workspaces': workspaces,
        }


# =============================================================================
# Prometheus Formatter
# =============================================================================

class PrometheusFormatter:
    """Formats metrics for Prometheus exposition format."""
    
    @staticmethod
    def format(metrics: Dict[str, Any]) -> str:
        """Format metrics as Prometheus text."""
        lines = []
        
        # Helper to add metric
        def add_metric(name: str, help_text: str, type_: str, value, labels: Dict = None):
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {type_}")
            if labels:
                label_str = ','.join(f'{k}="{v}"' for k, v in labels.items())
                lines.append(f"{name}{{{label_str}}} {value}")
            else:
                lines.append(f"{name} {value}")
        
        # Health metrics
        health = metrics.get('health', {})
        add_metric(
            'copilot_backup_last_run_timestamp',
            'Timestamp of the last backup run',
            'gauge',
            int(datetime.fromisoformat(health.get('last_backup_time', datetime.now().isoformat())).timestamp())
        )
        add_metric(
            'copilot_backup_age_seconds',
            'Age of the last backup in seconds',
            'gauge',
            health.get('backup_age_seconds', 0)
        )
        add_metric(
            'copilot_backup_healthy',
            'Whether the backup is considered healthy (1=healthy, 0=stale)',
            'gauge',
            1 if health.get('is_healthy', False) else 0
        )
        
        # Totals
        totals = metrics.get('totals', {})
        add_metric(
            'copilot_sessions_total',
            'Total number of chat sessions',
            'gauge',
            totals.get('sessions', 0)
        )
        add_metric(
            'copilot_messages_total',
            'Total number of messages across all sessions',
            'gauge',
            totals.get('messages', 0)
        )
        add_metric(
            'copilot_user_messages_total',
            'Total number of user messages',
            'gauge',
            totals.get('user_messages', 0)
        )
        add_metric(
            'copilot_assistant_messages_total',
            'Total number of assistant messages',
            'gauge',
            totals.get('assistant_messages', 0)
        )
        add_metric(
            'copilot_backup_total_size_bytes',
            'Total backup size in bytes',
            'gauge',
            totals.get('size_bytes', 0)
        )
        add_metric(
            'copilot_workspaces_total',
            'Total number of workspaces',
            'gauge',
            totals.get('workspaces', 0)
        )
        
        # Per-workspace metrics
        workspaces = metrics.get('workspaces', {})
        for ws_name, ws_data in workspaces.items():
            labels = {'workspace': ws_name}
            
            lines.append(f"# HELP copilot_workspace_sessions Sessions per workspace")
            lines.append(f"# TYPE copilot_workspace_sessions gauge")
            label_str = f'workspace="{ws_name}"'
            lines.append(f'copilot_workspace_sessions{{{label_str}}} {ws_data.get("session_count", 0)}')
            
            lines.append(f"# HELP copilot_workspace_messages Messages per workspace")
            lines.append(f"# TYPE copilot_workspace_messages gauge")
            lines.append(f'copilot_workspace_messages{{{label_str}}} {ws_data.get("total_messages", 0)}')
            
            lines.append(f"# HELP copilot_workspace_active_days Active days per workspace")
            lines.append(f"# TYPE copilot_workspace_active_days gauge")
            lines.append(f'copilot_workspace_active_days{{{label_str}}} {ws_data.get("active_days", 0)}')
        
        # Model usage metrics
        models = totals.get('models', {})
        for model, count in models.items():
            lines.append(f"# HELP copilot_model_usage_total Message count by model")
            lines.append(f"# TYPE copilot_model_usage_total gauge")
            lines.append(f'copilot_model_usage_total{{model="{model}"}} {count}')
        
        # Hourly distribution
        temporal = metrics.get('temporal', {})
        hourly = temporal.get('hourly', {})
        for hour, count in hourly.items():
            lines.append(f"# HELP copilot_hourly_sessions Session count by hour")
            lines.append(f"# TYPE copilot_hourly_sessions gauge")
            lines.append(f'copilot_hourly_sessions{{hour="{hour}"}} {count}')
        
        # Collection time
        lines.append(f"# HELP copilot_metrics_collection_seconds Time taken to collect metrics")
        lines.append(f"# TYPE copilot_metrics_collection_seconds gauge")
        lines.append(f'copilot_metrics_collection_seconds {metrics.get("collection_time_seconds", 0):.4f}')
        
        return '\n'.join(lines) + '\n'


# =============================================================================
# HTTP Handler
# =============================================================================

class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP request handler for metrics endpoints."""
    
    collector: MetricsCollector = None
    
    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug(f"HTTP: {args[0]}")
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        
        if path == '/metrics':
            self._serve_prometheus()
        elif path == '/api/metrics':
            self._serve_json(query)
        elif path == '/api/sessions':
            self._serve_sessions(query)
        elif path == '/api/workspaces':
            self._serve_workspaces(query)
        elif path == '/api/health':
            self._serve_health()
        elif path == '/':
            self._serve_index()
        else:
            self._send_404()
    
    def _serve_prometheus(self):
        """Serve Prometheus metrics."""
        try:
            metrics = self.collector.collect()
            output = PrometheusFormatter.format(metrics)
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(output.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error serving metrics: {e}")
            self._send_error(500, str(e))
    
    def _serve_json(self, query: Dict):
        """Serve JSON metrics."""
        try:
            metrics = self.collector.collect()
            
            # Apply filters
            if 'workspace' in query:
                ws_filter = query['workspace'][0]
                metrics['workspaces'] = {
                    k: v for k, v in metrics.get('workspaces', {}).items()
                    if ws_filter.lower() in k.lower()
                }
                metrics['sessions'] = [
                    s for s in metrics.get('sessions', [])
                    if ws_filter.lower() in s.get('project', '').lower()
                ]
            
            self._send_json(metrics)
        except Exception as e:
            logger.error(f"Error serving JSON: {e}")
            self._send_error(500, str(e))
    
    def _serve_sessions(self, query: Dict):
        """Serve session-level metrics."""
        try:
            metrics = self.collector.collect()
            sessions = metrics.get('sessions', [])
            
            # Apply filters
            if 'workspace' in query:
                ws_filter = query['workspace'][0]
                sessions = [s for s in sessions if ws_filter.lower() in s.get('project', '').lower()]
            
            if 'limit' in query:
                limit = int(query['limit'][0])
                sessions = sessions[:limit]
            
            self._send_json({'sessions': sessions, 'count': len(sessions)})
        except Exception as e:
            logger.error(f"Error serving sessions: {e}")
            self._send_error(500, str(e))
    
    def _serve_workspaces(self, query: Dict):
        """Serve workspace metrics."""
        try:
            metrics = self.collector.collect()
            workspaces = metrics.get('workspaces', {})
            self._send_json({'workspaces': workspaces, 'count': len(workspaces)})
        except Exception as e:
            logger.error(f"Error serving workspaces: {e}")
            self._send_error(500, str(e))
    
    def _serve_health(self):
        """Serve health check."""
        try:
            metrics = self.collector.collect()
            health = metrics.get('health', {})
            
            status = 200 if health.get('is_healthy', False) else 503
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(health).encode('utf-8'))
        except Exception as e:
            logger.error(f"Error serving health: {e}")
            self._send_error(500, str(e))
    
    def _serve_index(self):
        """Serve index page."""
        html = """<!DOCTYPE html>
<html>
<head><title>Copilot Chat Backup Metrics</title></head>
<body>
    <h1>Copilot Chat Backup Metrics</h1>
    <ul>
        <li><a href="/metrics">Prometheus Metrics</a></li>
        <li><a href="/api/metrics">JSON Metrics</a></li>
        <li><a href="/api/sessions">Sessions</a></li>
        <li><a href="/api/workspaces">Workspaces</a></li>
        <li><a href="/api/health">Health Check</a></li>
    </ul>
</body>
</html>"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
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
    
    def _send_404(self):
        """Send 404 response."""
        self._send_error(404, 'Not Found')


# =============================================================================
# Main
# =============================================================================

def main():
    """Main entry point."""
    backup_path = os.environ.get('BACKUP_PATH', str(Path.home() / 'copilot-chat-backups'))
    config_path = os.environ.get('CONFIG_PATH', '/app/config.yml')
    port = int(os.environ.get('METRICS_PORT', '8080'))
    
    logger.info(f"Starting Copilot Chat Metrics Exporter")
    logger.info(f"Backup path: {backup_path}")
    logger.info(f"Port: {port}")
    
    # Initialize collector
    collector = MetricsCollector(backup_path, config_path)
    MetricsHandler.collector = collector
    
    # Start server
    server = HTTPServer(('0.0.0.0', port), MetricsHandler)
    logger.info(f"Metrics server running on http://0.0.0.0:{port}")
    logger.info("Endpoints:")
    logger.info("  /metrics - Prometheus format")
    logger.info("  /api/metrics - JSON format")
    logger.info("  /api/sessions - Session details")
    logger.info("  /api/workspaces - Workspace details")
    logger.info("  /api/health - Health check")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
