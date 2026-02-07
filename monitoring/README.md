# Copilot Chat Backup - Monitoring & Search System

A complete observability and semantic search stack for your GitHub Copilot chat backup system.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Monitoring & Search Stack                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │   Grafana    │◄───│  Prometheus  │◄───│   Metrics    │                   │
│  │   :3000      │    │    :9090     │    │   Exporter   │                   │
│  │              │    │              │    │    :8080     │                   │
│  └──────────────┘    └──────────────┘    └──────┬───────┘                   │
│                                                  │                           │
│                                                  ▼                           │
│                                          ┌──────────────┐                   │
│                                          │   Backup     │                   │
│  ┌──────────────┐    ┌──────────────┐    │   Data       │                   │
│  │  Search API  │◄───│   Qdrant     │    │              │                   │
│  │    :8081     │    │ Vector DB    │    └──────────────┘                   │
│  │              │    │  :6333/6334  │                                        │
│  └──────────────┘    └──────────────┘                                        │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐                                       │
│  │    Redis     │    │    Node      │                                       │
│  │    :6379     │    │   Exporter   │                                       │
│  │   (cache)    │    │    :9100     │                                       │
│  └──────────────┘    └──────────────┘                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Start the Stack

\`\`\`bash
cd monitoring
docker-compose up -d
\`\`\`

### 2. Access Services

| Service         | URL                   | Description                |
| --------------- | --------------------- | -------------------------- |
| **Grafana**     | http://localhost:3001 | Dashboards & Visualization |
| **Prometheus**  | http://localhost:9091 | Metrics Database           |
| **Metrics API** | http://localhost:8082 | Custom Metrics Exporter    |
| **Search API**  | http://localhost:8083 | Semantic Search            |
| **Qdrant**      | http://localhost:6337 | Vector Database            |

### 3. Default Credentials

- **Grafana**: \`admin\` / \`copilot-admin-2024\`

## 📊 Dashboards

### Main Dashboard

Overview of all backup metrics:

- Total sessions, messages, and workspaces
- Backup health status and age
- Workspace distribution (pie charts)
- Model usage statistics
- Temporal analysis (hourly patterns)

### Session Explorer

Filter and explore individual sessions:

- Workspace filtering with dropdown
- Session comparison table
- Average messages per session
- Quick links to APIs

## 🔍 Search API

### Semantic Search

Search across all chat sessions using natural language:

\`\`\`bash

# Basic search

curl "http://localhost:8083/api/search?q=error%20handling"

# With filters

curl "http://localhost:8083/api/search?q=react%20hooks&project=aiconnects-hub&limit=5"

# Filter by role

curl "http://localhost:8083/api/search?q=async%20await&role=assistant"
\`\`\`

### Keyword Search

Find messages containing specific keywords:

\`\`\`bash

# Single keyword

curl "http://localhost:8083/api/keyword-search?keywords=python"

# Multiple keywords (all must match)

curl "http://localhost:8083/api/keyword-search?keywords=python,async,await"
\`\`\`

### Reindex

Trigger a full reindex of all sessions:

\`\`\`bash
curl "http://localhost:8083/api/reindex"
\`\`\`

### Statistics

Get search and database statistics:

\`\`\`bash
curl "http://localhost:8083/api/stats"
\`\`\`

## 📈 Metrics

### Available Prometheus Metrics

#### Backup Metrics

| Metric                               | Description                        |
| ------------------------------------ | ---------------------------------- |
| \`copilot_sessions_total\`           | Total number of chat sessions      |
| \`copilot_messages_total\`           | Total messages across all sessions |
| \`copilot_user_messages_total\`      | Total user messages                |
| \`copilot_assistant_messages_total\` | Total assistant messages           |
| \`copilot_backup_total_size_bytes\`  | Total backup size in bytes         |
| \`copilot_workspaces_total\`         | Total number of workspaces         |
| \`copilot_backup_healthy\`           | Backup health status (1=healthy)   |
| \`copilot_backup_age_seconds\`       | Age of last backup in seconds      |

#### Per-Workspace Metrics

| Metric                                             | Description               |
| -------------------------------------------------- | ------------------------- |
| \`copilot_workspace_sessions{workspace="..."}\`    | Sessions per workspace    |
| \`copilot_workspace_messages{workspace="..."}\`    | Messages per workspace    |
| \`copilot_workspace_active_days{workspace="..."}\` | Active days per workspace |

#### Search API Metrics

| Metric                             | Description            |
| ---------------------------------- | ---------------------- |
| \`copilot_search_total\`           | Total search requests  |
| \`copilot_search_success_total\`   | Successful searches    |
| \`copilot_search_errors_total\`    | Failed searches        |
| \`copilot_search_latency_avg_ms\`  | Average search latency |
| \`copilot_indexed_messages_total\` | Total indexed messages |
| \`copilot_qdrant_vectors_count\`   | Vectors in Qdrant      |

## ⚙️ Configuration

### Metrics Exporter

Edit \`metrics_config.yml\` to customize:

\`\`\`yaml
server:
port: 8080

backup:
path: "/data/backups"
scan_interval_seconds: 60

metrics:
sessions:
enabled: true
labels: - workspace - project
\`\`\`

## 🐳 Docker Commands

\`\`\`bash

# Start all services

docker-compose up -d

# View logs

docker-compose logs -f

# Restart specific service

docker-compose restart search-api

# Stop all services

docker-compose down

# Stop and remove volumes (clean start)

docker-compose down -v
\`\`\`

## 📁 File Structure

\`\`\`
monitoring/
├── docker-compose.yml # Main compose file
├── prometheus.yml # Prometheus configuration
├── alerting_rules.yml # Alert definitions
├── metrics_config.yml # Metrics exporter config
├── metrics_exporter.py # Custom metrics exporter
├── search_api.py # Semantic search API
├── Dockerfile.metrics # Metrics exporter image
├── Dockerfile.search # Search API image
├── requirements-metrics.txt # Python deps for metrics
├── requirements-search.txt # Python deps for search
├── grafana/
│ ├── provisioning/
│ │ ├── datasources/
│ │ │ └── prometheus.yml # Prometheus datasource
│ │ └── dashboards/
│ │ └── dashboards.yml # Dashboard provider
│ └── dashboards/
│ ├── copilot-backup.json # Main dashboard
│ └── sessions-explorer.json # Session explorer
└── README.md # This file
\`\`\`

## 🔒 Security Notes

1. **Change default passwords** before production use
2. **Use environment variables** for sensitive data
3. **Restrict network access** in production
4. **Enable HTTPS** with reverse proxy (nginx/traefik)

## 📄 License

MIT License - see LICENSE file for details.
