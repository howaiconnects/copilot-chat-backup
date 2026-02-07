# 📋 Monorepo Import Checklist - For Moderators

## Executive Summary

This document provides a **complete checklist** for importing the Copilot Chat Backup project into your monorepo. Follow each step to ensure proper integration while maintaining all functionalities.

---

## 🎯 Project Overview

**Project Name**: Copilot Chat Backup  
**Purpose**: Backup, analyze, and monitor GitHub Copilot chat sessions  
**Type**: Developer Tool / Observability  
**Location in Monorepo**: `tools/copilot-chat-backup/` (recommended)  
**Dependencies**: Python 3.8+, Docker 20.10+, Docker Compose 2.0+  
**Resource Usage**: ~1.5 GB disk, ~1 GB RAM, 7 network ports  
**Maturity**: Production-ready, fully tested

---

## ✅ Pre-Import Checklist

### System Requirements

- [ ] Python 3.8+ installed
- [ ] Docker 20.10+ installed
- [ ] Docker Compose 2.0+ installed
- [ ] Git 2.30+ installed
- [ ] At least 2 GB free disk space
- [ ] At least 2 GB free RAM

### Port Availability Check

Run this command to check default ports:

```bash
for port in 9091 3001 8082 8083 6337 6390 9101; do
  if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "❌ Port $port is IN USE"
  else
    echo "✅ Port $port is available"
  fi
done
```

- [ ] All 7 ports available (or alternative ports identified)

### Monorepo Structure

- [ ] Monorepo root directory identified
- [ ] Target location decided: `tools/copilot-chat-backup/` (recommended)
- [ ] Write permissions verified on target directory
- [ ] Git repository initialized and accessible

---

## 📥 Import Steps

### Step 1: Automated Import (Recommended)

**Use the provided import script:**

```bash
# From the copilot-chat-backup source directory
./import-to-monorepo.sh
```

The script will:

- ✅ Check all prerequisites
- ✅ Copy all files to target location
- ✅ Create `.env` file with default configuration
- ✅ Update monorepo `.gitignore`
- ✅ Set proper file permissions
- ✅ Test installation

**Checklist:**

- [ ] Script executed successfully
- [ ] No errors in output
- [ ] Files copied to target location
- [ ] Configuration files created

---

### Step 2: Manual Import (Alternative)

If automated script fails, use manual steps:

```bash
# Set variables
SOURCE="/path/to/copilot-chat-backup"
TARGET="/path/to/monorepo/tools/copilot-chat-backup"

# Create target directory
mkdir -p "$TARGET"

# Copy files
cp -r "$SOURCE/"* "$TARGET/"

# Create .env from template
cp "$TARGET/.env.example" "$TARGET/.env"

# Make scripts executable
chmod +x "$TARGET"/*.sh

# Update .gitignore (see MONOREPO_INTEGRATION.md)
```

**Checklist:**

- [ ] All files copied
- [ ] `.env` file created
- [ ] Scripts are executable
- [ ] `.gitignore` updated

---

## 🔧 Configuration

### Step 3: Environment Configuration

**Edit** `tools/copilot-chat-backup/.env`:

```bash
cd tools/copilot-chat-backup
nano .env
```

**Verify/Update:**

- [ ] All port numbers are correct (no conflicts)
- [ ] `COMPOSE_PROJECT_NAME=copilot-backup` (for Docker isolation)
- [ ] Grafana credentials are set
- [ ] Database path is relative: `./copilot_backup.db`

### Step 4: GitHub Token Setup

**Create** `tools/copilot-chat-backup/config.json`:

```bash
cp config.json.example config.json
nano config.json
```

**Add:**

```json
{
  "github_token": "ghp_xxxxxxxxxxxxxxxxxxxx",
  "github_username": "actual-username"
}
```

**Checklist:**

- [ ] `config.json` created
- [ ] Valid GitHub token added (with `read:user` scope)
- [ ] File is in `.gitignore` (verify: `git status` should not show it)

---

## 🐳 Docker Services

### Step 5: Start Monitoring Stack

```bash
cd tools/copilot-chat-backup
./start-monitoring.sh start
```

**Expected output:**

```
✅ Starting Docker services...
✅ Waiting for services to be ready...
✅ All services are healthy!
```

**Checklist:**

- [ ] All 7 services started without errors
- [ ] Health checks passing
- [ ] No port conflict errors
- [ ] Docker containers visible: `docker ps | grep copilot-backup`

### Step 6: Verify Service Health

```bash
./start-monitoring.sh status
```

**Expected:**

```
Prometheus:       ✅ Healthy (http://localhost:9091)
Grafana:          ✅ Healthy (http://localhost:3001)
Metrics Exporter: ✅ Healthy (http://localhost:8082)
...
```

**Checklist:**

- [ ] All services showing ✅ Healthy
- [ ] All URLs accessible
- [ ] No connection errors

---

## 📊 Database & Backup

### Step 7: Test Database

```bash
cd tools/copilot-chat-backup
python3 db_manager.py --stats
```

**Expected output:**

```
=== Backup Statistics ===
Total Backups: 1
Unique Sessions: 256
Total Messages: 2058
Unique Workspaces: 84
```

**Checklist:**

- [ ] Command executed successfully
- [ ] Database file exists: `copilot_backup.db`
- [ ] Stats displayed correctly

### Step 8: Run First Backup

```bash
python3 backup-copilot-chats.py
```

**Expected:**

```
Fetching chat sessions...
Found 256 sessions
Saved 2058 messages
Backup complete!
```

**Checklist:**

- [ ] Backup completed without errors
- [ ] Messages saved locally
- [ ] Database updated with new data

### Step 9: Sync to Database

```bash
python3 sync-to-database.py
```

**Expected:**

```
✅ Saved backup run #2
Summary: 256 sessions, 2058 messages, 84 workspaces
```

**Checklist:**

- [ ] Sync completed successfully
- [ ] Database updated
- [ ] Stats command shows new data

---

## 📈 Grafana Dashboard

### Step 10: Access Grafana

1. Open browser: http://localhost:3001
2. Login:
   - Username: `admin`
   - Password: `copilot-admin-2024`

**Checklist:**

- [ ] Grafana loads successfully
- [ ] Login successful
- [ ] Prometheus datasource connected (check Status)

### Step 11: Verify Dashboards

Navigate to: **Dashboards** → **Browse**

**Expected dashboards:**

1. Copilot Backup Overview
2. Sessions Explorer

**Checklist:**

- [ ] Both dashboards visible
- [ ] Dashboards load without errors
- [ ] Data populating in panels
- [ ] No "No Data" errors (after backup run)

---

## 🔍 API Testing

### Step 12: Test Metrics API

```bash
# Health check
curl http://localhost:8082/api/health

# Get metrics
curl http://localhost:8082/api/metrics | jq '.summary'

# Get sessions
curl http://localhost:8082/api/sessions | jq '.[0]'
```

**Checklist:**

- [ ] Health endpoint returns `{"status": "healthy"}`
- [ ] Metrics endpoint returns valid JSON
- [ ] Sessions endpoint returns array of sessions

### Step 13: Test Search API

```bash
# Health check
curl http://localhost:8083/health

# Search
curl -X POST http://localhost:8083/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 5}' | jq '.'
```

**Checklist:**

- [ ] Health endpoint returns `{"status": "healthy"}`
- [ ] Search returns results (after vectorization complete)

---

## 📝 Documentation

### Step 14: Verify Documentation

**Check these files exist and are readable:**

- [ ] `README.md` - Main documentation
- [ ] `SETUP_SUMMARY.md` - Quick start guide
- [ ] `MONOREPO_INTEGRATION.md` - **This guide** (27 KB)
- [ ] `ARCHITECTURE.md` - System architecture (15 KB)
- [ ] `README_DATABASE.md` - Database documentation
- [ ] `monitoring/README.md` - Monitoring setup
- [ ] `monitoring/DASHBOARDS.md` - Dashboard specs

### Step 15: Update Monorepo README

**Add to your monorepo's main README.md:**

````markdown
## Developer Tools

### Copilot Chat Backup

Backup and analyze GitHub Copilot chat sessions with full observability.

**Location**: [`tools/copilot-chat-backup/`](tools/copilot-chat-backup/)

**Quick Start**:

```bash
cd tools/copilot-chat-backup

# Start monitoring
./start-monitoring.sh start

# Run backup
python3 backup-copilot-chats.py

# View stats
python3 db_manager.py --stats

# Access Grafana
open http://localhost:3001
```
````

**Documentation**: See [tools/copilot-chat-backup/README.md](tools/copilot-chat-backup/README.md)

````

**Checklist:**
- [ ] Monorepo README updated
- [ ] Link to project documentation added
- [ ] Quick start commands included

---

## 🔐 Security Review

### Step 16: Secrets Management

**Verify these files are NOT in git:**
```bash
cd tools/copilot-chat-backup
git status
````

**Must be excluded:**

- [ ] `config.json` (GitHub token)
- [ ] `.env` (environment variables)
- [ ] `backups/` (backup files)
- [ ] `monitoring/grafana/data/` (Grafana data)

**Can be included:**

- [x] `copilot_backup.db` (SQLite database)
- [x] `config.json.example` (template)
- [x] `.env.example` (template)

### Step 17: File Permissions

```bash
# Check permissions
ls -la tools/copilot-chat-backup/

# Should see:
# -rwxr-xr-x  *.sh (executable)
# -rw-r--r--  *.py (readable)
# -rw-------  config.json (private, if exists)
```

**Checklist:**

- [ ] Shell scripts are executable
- [ ] Python scripts are readable
- [ ] Secrets files have restrictive permissions (if present)

---

## 🧪 Integration Testing

### Step 18: Full Workflow Test

Run complete workflow:

```bash
cd tools/copilot-chat-backup

# 1. Start services
./start-monitoring.sh start

# 2. Check status
./start-monitoring.sh status

# 3. Run backup
python3 backup-copilot-chats.py

# 4. Sync to database
python3 sync-to-database.py

# 5. View stats
python3 db_manager.py --stats

# 6. Check metrics API
curl http://localhost:8082/api/metrics | jq '.summary'

# 7. Open Grafana
open http://localhost:3001
```

**Checklist:**

- [ ] All commands execute without errors
- [ ] Services remain healthy throughout
- [ ] Data flows from backup → database → API → Grafana
- [ ] No resource exhaustion (check `top`)

### Step 19: Monorepo Integration Test

**If using package.json scripts:**

```bash
# From monorepo root
npm run copilot:stats
npm run copilot:monitor:status
```

**If using Makefile:**

```bash
# From monorepo root
make copilot-stats
make copilot-monitor-status
```

**Checklist:**

- [ ] Monorepo scripts work correctly
- [ ] Commands execute from monorepo root
- [ ] Output is correct

---

## 📊 Resource Validation

### Step 20: Resource Usage Check

```bash
# Docker stats
docker stats --no-stream | grep copilot-backup

# Disk usage
du -sh tools/copilot-chat-backup/

# Memory usage
ps aux | grep -E "(python|docker)" | grep copilot
```

**Expected:**

- Total disk: ~1.5 GB
- Total RAM: ~1 GB
- CPU: 5-15% during backup, <5% idle

**Checklist:**

- [ ] Disk usage within limits
- [ ] Memory usage acceptable
- [ ] CPU usage reasonable
- [ ] No resource warnings

### Step 21: Port Usage Verification

```bash
# Check listening ports
netstat -tuln | grep -E "(9091|3001|8082|8083|6337|6390|9101)"
```

**Expected:** All 7 ports listening

**Checklist:**

- [ ] All ports listening
- [ ] No unexpected ports
- [ ] No conflicts with other services

---

## 📦 Git Repository

### Step 22: Commit Changes

```bash
cd /path/to/monorepo
git add tools/copilot-chat-backup/
git status
```

**Should see:**

- Modified: `.gitignore`, `README.md`
- Added: ~30 new files

```bash
git commit -m "feat: add copilot chat backup tool

- Complete monitoring stack (Prometheus, Grafana, Qdrant)
- SQLite database for local metrics storage
- CLI tools for queries and management
- Automated backup system
- Semantic search capability
- Full documentation and guides

Closes #XXX"
```

**Checklist:**

- [ ] All files staged correctly
- [ ] Secrets excluded from commit
- [ ] Database included (if desired)
- [ ] Commit message descriptive

### Step 23: Push to Remote

```bash
git push origin main
```

**Checklist:**

- [ ] Push successful
- [ ] CI/CD passes (if applicable)
- [ ] No secrets leaked (GitHub Secret Scanning)

---

## 🎓 Team Onboarding

### Step 24: Team Training

**Share with team:**

1. **Location**: `tools/copilot-chat-backup/`
2. **Quick Start**: `README.md`
3. **Integration Guide**: `MONOREPO_INTEGRATION.md`
4. **Architecture**: `ARCHITECTURE.md`

**Training checklist:**

- [ ] Team notified of new tool
- [ ] Documentation shared
- [ ] Quick start guide provided
- [ ] Support channel created (e.g., Slack)

### Step 25: Access Setup

**For each team member:**

```bash
# 1. Create their config.json
cd tools/copilot-chat-backup
cp config.json.example config.json
# Add their GitHub token

# 2. Test access
python3 db_manager.py --stats

# 3. Access Grafana
# URL: http://localhost:3001
# User: admin / copilot-admin-2024
```

**Checklist:**

- [ ] Team members can run backups
- [ ] Team members can access Grafana
- [ ] Team members can query database

---

## 🔍 CI/CD Integration (Optional)

### Step 26: GitHub Actions

**Create** `.github/workflows/copilot-backup.yml`:

```yaml
name: Copilot Backup

on:
  schedule:
    - cron: "0 2 * * *" # Daily at 2 AM
  workflow_dispatch:

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Configure token
        run: |
          cd tools/copilot-chat-backup
          echo '{"github_token": "${{ secrets.GITHUB_TOKEN }}", "github_username": "${{ github.actor }}"}' > config.json

      - name: Run backup
        run: |
          cd tools/copilot-chat-backup
          python3 backup-copilot-chats.py
          python3 sync-to-database.py

      - name: Commit database
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add tools/copilot-chat-backup/copilot_backup.db
          git diff --staged --quiet || git commit -m "chore: update copilot backup database [skip ci]"
          git push
```

**Checklist:**

- [ ] Workflow file created
- [ ] Workflow triggered successfully
- [ ] Backup runs automatically
- [ ] Database commits work

---

## ✅ Final Validation

### Step 27: Complete System Test

Run this comprehensive test:

```bash
#!/bin/bash
cd tools/copilot-chat-backup

echo "=== Full System Test ==="

# 1. Services
echo "1. Testing services..."
./start-monitoring.sh status || exit 1

# 2. Database
echo "2. Testing database..."
python3 db_manager.py --stats || exit 1

# 3. Backup
echo "3. Testing backup..."
python3 backup-copilot-chats.py || exit 1

# 4. Sync
echo "4. Testing sync..."
python3 sync-to-database.py || exit 1

# 5. APIs
echo "5. Testing APIs..."
curl -f http://localhost:8082/api/health || exit 1
curl -f http://localhost:3001/api/health || exit 1

echo "✅ All tests passed!"
```

**Checklist:**

- [ ] All tests pass
- [ ] No errors in output
- [ ] Services remain healthy

---

## 📋 Sign-Off Checklist

### Final Review (For Moderators)

**Functionality:**

- [ ] ✅ All 7 Docker services running
- [ ] ✅ Database accessible and queryable
- [ ] ✅ Backup script works
- [ ] ✅ Grafana dashboards load
- [ ] ✅ APIs responding correctly
- [ ] ✅ Search functionality works

**Integration:**

- [ ] ✅ No port conflicts
- [ ] ✅ No dependency conflicts
- [ ] ✅ Monorepo scripts work
- [ ] ✅ Documentation complete
- [ ] ✅ Git repository clean

**Security:**

- [ ] ✅ Secrets excluded from git
- [ ] ✅ Proper file permissions
- [ ] ✅ No exposed credentials
- [ ] ✅ Network isolated

**Performance:**

- [ ] ✅ Resource usage acceptable
- [ ] ✅ No performance degradation
- [ ] ✅ Services stable

**Documentation:**

- [ ] ✅ README updated
- [ ] ✅ Team notified
- [ ] ✅ Training provided
- [ ] ✅ Support channel created

---

## ✅ Approval

**Reviewed by**: ************\_\_\_************  
**Date**: ************\_\_\_************  
**Status**: [ ] Approved [ ] Needs Changes

**Comments**:

```
_________________________________________________
_________________________________________________
_________________________________________________
```

---

## 📞 Support

**Issues?** See troubleshooting in `MONOREPO_INTEGRATION.md`  
**Questions?** Contact: [Insert team contact]  
**Documentation**: `tools/copilot-chat-backup/README.md`

---

## 🎉 Success!

Once all checkboxes are complete, the integration is successful!

**Expected Outcome:**

- ✅ Project fully integrated into monorepo
- ✅ All functionalities preserved
- ✅ Team trained and onboarded
- ✅ No conflicts or issues
- ✅ Ready for production use

**Next Steps:**

1. Monitor resource usage over first week
2. Gather team feedback
3. Create first custom Grafana dashboard
4. Schedule regular database backups
5. Consider CI/CD automation

---

**Import Date**: ************\_\_\_************  
**Monorepo Version**: ************\_\_\_************  
**Imported By**: ************\_\_\_************

**🚀 Welcome to Copilot Chat Backup!**
