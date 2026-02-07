# Complete Integrated Setup Guide

**Copilot Chat Backup** with Azure AI Foundry, Qdrant, Prometheus & Grafana

All services are now fully integrated and preconfigured to work seamlessly together.

---

## 🎯 What's Integrated

### ✅ Core Services

- **SQLite Database** - Chat metadata and content storage
- **Qdrant v1.7.4** - Vector database for semantic search (port 6337)
- **Azure AI Foundry** - Cloud embeddings via OpenAI API
- **Prometheus v2.48.0** - Metrics collection (port 9091)
- **Grafana v10.2.2** - Visualization dashboards (port 3001)

### ✅ APIs & Endpoints

- **Metrics Exporter** - Port 8082 - Workspace, session, date metrics
- **Search API** - Port 8083 - Semantic search endpoint
- **Qdrant REST API** - Port 6337 - Vector operations
- **Qdrant gRPC** - Port 6338 - High-performance queries

### ✅ Preconfigured Dashboards

1. **Copilot Backup Overview** - General health and statistics
2. **Sessions Explorer** - Detailed session analytics
3. **Vector Search Analytics** - Embedding and search metrics
4. **Workspace Explorer** - Per-workspace breakdowns

---

## 🚀 One-Command Setup

```bash
# Run the complete setup script
./setup-vector-search.sh
```

This script will:

1. ✅ Check prerequisites (Docker, Python)
2. ✅ Install Python dependencies
3. ✅ Create `.env` configuration (prompts for Azure AI keys)
4. ✅ Start all Docker services
5. ✅ Verify health of all services
6. ✅ Optionally sync chats to Qdrant
7. ✅ Display access URLs and quick commands

---

## 📝 Manual Setup (Step by Step)

### Step 1: Configure Azure AI Foundry

```bash
# Copy the example file
cp .env.vector.example .env

# Edit .env and add your credentials:
# AZURE_OPENAI_API_KEY=your-key-here
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
# AZURE_OPENAI_DEPLOYMENT=text-embedding-3-small
```

**Get credentials from:**

- VSCode AI Toolkit extension
- Azure Portal → Your OpenAI Resource
- Azure AI Foundry portal

### Step 2: Install Dependencies

```bash
pip install -r requirements-vector.txt
```

### Step 3: Start Services

```bash
cd monitoring
docker-compose up -d
cd ..
```

**Services started:**

- ✅ Qdrant on port 6337
- ✅ Prometheus on port 9091
- ✅ Grafana on port 3001
- ✅ Metrics Exporter on port 8082
- ✅ Search API on port 8083

### Step 4: Verify Services

```bash
# Qdrant health
curl http://localhost:6337/health

# Prometheus health
curl http://localhost:9091/-/healthy

# Grafana health
curl http://localhost:3001/api/health

# Metrics endpoint
curl http://localhost:8082/metrics
```

### Step 5: Sync Chats to Qdrant

```bash
# Load environment variables
source .env

# Sync all chats
python3 vectorize_chats.py --sync

# Or sync specific workspace
python3 vectorize_chats.py --sync --workspace "my-project"
```

---

## 🔍 Using the System

### Semantic Search

```bash
# Basic search
python3 vectorize_chats.py --search "how to deploy azure functions"

# Search in workspace
python3 vectorize_chats.py --search "react hooks" --workspace "frontend-app"

# Get more results
python3 vectorize_chats.py --search "database migrations" --limit 10
```

### Check Collection Status

```bash
python3 vectorize_chats.py --info
```

**Output:**

```
📊 Collection Info:
   name: copilot_chats
   vectors_count: 156
   points_count: 156
   status: green
   vector_size: 1536
   distance: COSINE
```

### Direct Database Queries

```bash
# Using db_manager.py
python3 db_manager.py --workspace "my-project"
python3 db_manager.py --stats
python3 db_manager.py --list
```

---

## 📊 Grafana Dashboards

Access Grafana: **http://localhost:3001**

**Login:** admin / copilot-admin-2024

### Dashboard 1: Copilot Backup Overview

- Total sessions, messages, workspaces
- Recent activity timeline
- Backup health status
- Token usage trends

### Dashboard 2: Sessions Explorer

- Session details table (sortable, searchable)
- Message count per session
- Session duration analysis
- Token distribution

### Dashboard 3: Vector Search Analytics (NEW)

- **Sessions by Workspace** - Line chart showing growth
- **Total Messages** - Gauge with thresholds
- **Session Distribution** - Pie chart by workspace
- **Daily Sessions** - Bar chart (last 30 days)
- **Key Metrics** - Total sessions, avg messages, avg tokens, max messages

### Dashboard 4: Workspace Explorer (NEW)

- **Workspace Overview Table** - Sessions, messages, tokens per workspace
- **Messages by Workspace** - Trend lines with statistics
- **Token Usage by Workspace** - Bar chart comparison
- **Workspace Filter** - Dropdown to filter by specific workspace(s)

---

## 🔧 Enhanced Metrics

All metrics are now exposed at **http://localhost:8082/metrics**

### Workspace Metrics (NEW)

```
copilot_backup_workspace_sessions{workspace="frontend-app"} 45
copilot_backup_workspace_messages{workspace="frontend-app"} 892
copilot_backup_workspace_tokens{workspace="frontend-app"} 12543
```

### Date Metrics (NEW)

```
copilot_backup_daily_sessions{date="2024-12-28"} 12
copilot_backup_daily_workspaces{date="2024-12-28"} 5
copilot_backup_daily_messages{date="2024-12-28"} 203
```

### Session Statistics (NEW)

```
copilot_backup_avg_messages_per_session 19.8
copilot_backup_avg_tokens_per_session 278.6
copilot_backup_max_messages_in_session 67
```

### Existing Metrics

```
copilot_backup_sessions_total 156
copilot_backup_messages_total 3089
copilot_backup_workspaces_total 8
copilot_backup_last_backup_timestamp 1703782800
```

---

## 🎨 Query Examples

### Find Chats by Topic

```bash
# Deployment-related
python3 vectorize_chats.py --search "deployment CI/CD azure"

# React development
python3 vectorize_chats.py --search "react performance hooks"

# Database work
python3 vectorize_chats.py --search "SQL queries optimization"
```

### Filter by Workspace

```bash
# Backend work
python3 vectorize_chats.py --search "API endpoints" --workspace "backend-api"

# Frontend work
python3 vectorize_chats.py --search "components" --workspace "frontend-app"
```

### Time-based Queries (via Grafana)

1. Open Grafana
2. Go to "Vector Search Analytics"
3. Use time picker (top right) to select date range
4. View "Daily Sessions" panel for trends

### Workspace Comparison (via Grafana)

1. Open "Workspace Explorer" dashboard
2. Use workspace dropdown to select multiple workspaces
3. Compare sessions, messages, and token usage
4. Sort table by any column

---

## 🔄 Automated Sync

### Option 1: Cron Job

```bash
# Add to crontab (edit with: crontab -e)
# Sync every hour
0 * * * * cd /home/adham/Dev/copilot-chat-backup && /usr/bin/python3 vectorize_chats.py --sync >> logs/vector-sync.log 2>&1
```

### Option 2: Event-Driven

Modify `backup-copilot-chats.py` to trigger sync after each backup:

```python
# Add to end of backup function
def after_backup_hook():
    import subprocess
    subprocess.run(["python3", "vectorize_chats.py", "--sync"], check=False)
```

### Option 3: Manual

```bash
# After running backups
./backup-copilot-chats.sh && python3 vectorize_chats.py --sync
```

---

## 🔐 Security Best Practices

### API Keys

- ✅ Never commit `.env` files
- ✅ Use environment variables
- ✅ Rotate keys regularly
- ✅ Use managed identities in production

### Network Security

- ✅ All services run in isolated Docker network
- ✅ Ports only exposed to localhost
- ✅ Use reverse proxy (nginx) for production
- ✅ Enable TLS for external access

### Data Protection

- ✅ Database file is git-tracked (metadata only)
- ✅ Vector data in Docker volume (not in git)
- ✅ Backups stored outside repo
- ✅ Regular database snapshots

---

## 📈 Monitoring & Alerts

### Prometheus Alerts (Configured)

```yaml
# Low backup frequency
- alert: LowBackupFrequency
  expr: rate(copilot_backup_sessions_total[1h]) < 0.01
  for: 24h
  annotations:
    summary: "No new backups in 24 hours"

# High error rate
- alert: HighErrorRate
  expr: rate(copilot_backup_errors_total[5m]) > 0.1
  for: 5m
  annotations:
    summary: "Backup errors detected"
```

### Grafana Alerts

Set up alerts in each dashboard:

1. Edit panel → Alert tab
2. Configure conditions
3. Add notification channel (email, Slack, etc.)

---

## 🐛 Troubleshooting

### Qdrant Not Connecting

```bash
# Check if running
docker ps | grep qdrant

# Check logs
docker logs copilot-qdrant

# Restart
cd monitoring && docker-compose restart qdrant
```

### Azure AI Foundry Auth Errors

```bash
# Verify credentials
echo $AZURE_OPENAI_API_KEY
echo $AZURE_OPENAI_ENDPOINT

# Test connection
curl -H "api-key: $AZURE_OPENAI_API_KEY" \
  "$AZURE_OPENAI_ENDPOINT/openai/deployments/$AZURE_OPENAI_DEPLOYMENT/embeddings?api-version=2024-02-01" \
  -H "Content-Type: application/json" \
  -d '{"input": "test"}'
```

### Metrics Not Showing in Grafana

```bash
# Check Prometheus targets
open http://localhost:9091/targets

# Check metrics endpoint directly
curl http://localhost:8082/metrics | grep copilot_backup

# Refresh Grafana datasource
# Grafana → Configuration → Data Sources → Prometheus → Save & Test
```

### Docker Services Not Starting

```bash
# Check port conflicts
sudo lsof -i :6337
sudo lsof -i :9091
sudo lsof -i :3001

# View all logs
cd monitoring && docker-compose logs

# Restart all services
docker-compose down && docker-compose up -d
```

---

## 📚 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Copilot Chat Backup                     │
│                    Integrated Architecture                   │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐
│  GitHub API  │  ← Fetch conversations
└──────┬───────┘
       │
       ▼
┌──────────────────┐      ┌─────────────────┐
│ backup-copilot   │ ───► │  SQLite DB      │  Metadata + Content
│    -chats.py     │      │  copilot_backup │
└──────────────────┘      └────────┬────────┘
                                   │
                    ┌──────────────┴───────────────┐
                    │                              │
                    ▼                              ▼
          ┌──────────────────┐          ┌──────────────────┐
          │ vectorize_chats  │          │   db_manager.py  │
          │       .py        │          │   (CLI Query)    │
          └────────┬─────────┘          └──────────────────┘
                   │
                   │ Azure AI Foundry
                   │ (Generate Embeddings)
                   │
                   ▼
          ┌──────────────────┐
          │  Qdrant (6337)   │  Vector Search
          │  copilot_chats   │
          └────────┬─────────┘
                   │
        ┌──────────┴──────────┬──────────────────┐
        │                     │                  │
        ▼                     ▼                  ▼
┌──────────────┐    ┌──────────────┐   ┌──────────────┐
│ Metrics API  │    │  Search API  │   │  Prometheus  │
│   (8082)     │    │   (8083)     │   │   (9091)     │
└──────┬───────┘    └──────┬───────┘   └──────┬───────┘
       │                   │                   │
       └───────────────────┴───────────────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  Grafana (3001)  │
                  │  4 Dashboards    │
                  └──────────────────┘
```

---

## 🎯 Use Cases

### 1. Find Similar Conversations

```bash
python3 vectorize_chats.py --search "typescript interfaces generics"
```

### 2. Workspace Analytics

- Open Grafana → Workspace Explorer
- Filter by workspace
- View trends over time

### 3. Daily Activity Report

- Open Grafana → Vector Search Analytics
- View "Daily Sessions" panel
- Identify peak activity days

### 4. Token Usage Tracking

- Open Grafana → Sessions Explorer
- Sort by tokens descending
- Identify high-token conversations

### 5. Cross-Project Search

```bash
# Find all auth-related discussions
python3 vectorize_chats.py --search "authentication JWT tokens" --limit 20
```

---

## 🚀 Next Steps

1. **Run the setup script:**

   ```bash
   ./setup-vector-search.sh
   ```

2. **Explore Grafana dashboards:**

   - http://localhost:3001

3. **Try semantic search:**

   ```bash
   python3 vectorize_chats.py --search "your first query"
   ```

4. **Set up automated sync:**

   - Add cron job (see Automated Sync section)

5. **Customize dashboards:**
   - Add your own panels
   - Create custom alerts
   - Export and share

---

## 📖 Related Documentation

- [VECTOR_SEARCH_GUIDE.md](VECTOR_SEARCH_GUIDE.md) - Detailed vector search guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [SETUP_SUMMARY.md](SETUP_SUMMARY.md) - Original setup guide
- [README_DATABASE.md](README_DATABASE.md) - Database documentation
- [MONOREPO_INTEGRATION.md](MONOREPO_INTEGRATION.md) - Monorepo integration

---

**Questions? Issues?** Check the troubleshooting section or open an issue on GitHub.

**Status:** ✅ All services integrated and production-ready!
