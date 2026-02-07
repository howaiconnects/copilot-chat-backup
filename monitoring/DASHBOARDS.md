# Copilot Chat Backup - Dashboard Requirements

This document outlines the custom Grafana dashboards needed for comprehensive monitoring and analysis of the Copilot Chat Backup system.

## 📊 Dashboard Inventory

| #   | Dashboard                 | Status     | Priority | Description                            |
| --- | ------------------------- | ---------- | -------- | -------------------------------------- |
| 1   | **Main Overview**         | ✅ Created | P0       | High-level system overview and health  |
| 2   | **Session Explorer**      | ✅ Created | P0       | Filter and explore individual sessions |
| 3   | **Workspace Analytics**   | ⬜ TODO    | P1       | Deep-dive into workspace-level metrics |
| 4   | **Conversation Insights** | ⬜ TODO    | P1       | Message patterns and content analysis  |
| 5   | **Search Analytics**      | ⬜ TODO    | P1       | Vector search usage and performance    |
| 6   | **System Health**         | ⬜ TODO    | P2       | Infrastructure and service health      |
| 7   | **Trends & Forecasting**  | ⬜ TODO    | P2       | Historical trends and predictions      |
| 8   | **Alerts Dashboard**      | ⬜ TODO    | P2       | Active alerts and incident tracking    |

---

## 1. Main Overview Dashboard ✅

**File:** `copilot-backup.json`  
**Status:** Created

### Panels Included:

- [x] Total Sessions (stat)
- [x] Total Messages (stat)
- [x] Total Workspaces (stat)
- [x] Backup Health Status (stat)
- [x] Backup Size (stat with bytes)
- [x] Backup Age (stat with time)
- [x] Workspace Distribution (pie chart)
- [x] Messages by Workspace (pie chart)
- [x] Sessions Over Time (time series)
- [x] Messages Per Session Distribution (bar gauge)
- [x] Model Usage Statistics (bar chart)
- [x] Hourly Activity Pattern (heatmap)
- [x] User vs Assistant Messages (gauge)
- [x] Top 10 Active Workspaces (table)
- [x] Recent Activity Timeline (time series)

---

## 2. Session Explorer Dashboard ✅

**File:** `sessions-explorer.json`  
**Status:** Created

### Panels Included:

- [x] Workspace Dropdown Filter (variable)
- [x] Sessions Table with Metrics
- [x] Session Comparison Chart
- [x] Average Messages Per Session (stat)
- [x] Quick Links Panel (text)

---

## 3. Workspace Analytics Dashboard ⬜

**File:** `workspace-analytics.json`  
**Status:** TODO  
**Priority:** P1

### Required Panels:

- [ ] Workspace Selector (multi-select variable)
- [ ] Workspace Activity Heatmap (calendar view)
- [ ] Sessions per Workspace Over Time (stacked area)
- [ ] Message Volume by Workspace (bar chart)
- [ ] Workspace Comparison Table (sortable)
- [ ] First/Last Activity Dates per Workspace
- [ ] Workspace Growth Rate (percentage change)
- [ ] Active Days per Workspace (bar chart)
- [ ] Project Distribution within Workspace (pie)
- [ ] Message Length Distribution by Workspace (histogram)

### Data Sources Needed:

```promql
# Sessions by workspace
copilot_workspace_sessions{workspace="$workspace"}

# Messages by workspace
copilot_workspace_messages{workspace="$workspace"}

# Active days
copilot_workspace_active_days{workspace="$workspace"}
```

---

## 4. Conversation Insights Dashboard ⬜

**File:** `conversation-insights.json`  
**Status:** TODO  
**Priority:** P1

### Required Panels:

- [ ] Message Role Distribution (donut - user/assistant/system)
- [ ] Average Conversation Length (stat)
- [ ] Longest Conversations (top 10 table)
- [ ] Shortest Conversations (bottom 10 table)
- [ ] Message Timing Patterns (hourly heatmap)
- [ ] Weekly Activity Pattern (day-of-week chart)
- [ ] Response Time Analysis (if timestamps available)
- [ ] Model Usage Distribution (pie chart)
- [ ] Tool Usage Frequency (bar chart)
- [ ] Code Block Detection Rate (gauge)
- [ ] Language Distribution in Code Blocks (pie)
- [ ] Conversation Topics Word Cloud (if text analysis available)

### Data Sources Needed:

```promql
# User messages
copilot_user_messages_total

# Assistant messages
copilot_assistant_messages_total

# Model usage
copilot_model_usage{model="$model"}

# Hourly patterns
copilot_messages_by_hour{hour="$hour"}
```

---

## 5. Search Analytics Dashboard ⬜

**File:** `search-analytics.json`  
**Status:** TODO  
**Priority:** P1

### Required Panels:

- [ ] Total Searches (stat counter)
- [ ] Search Success Rate (gauge)
- [ ] Average Search Latency (stat in ms)
- [ ] Search Latency Distribution (histogram)
- [ ] Searches Over Time (time series)
- [ ] Top Search Queries (table)
- [ ] Search by Type (semantic vs keyword - pie)
- [ ] Results per Search Distribution (histogram)
- [ ] Zero-Result Searches (counter + list)
- [ ] Qdrant Vector Count (stat)
- [ ] Qdrant Collection Health (status)
- [ ] Index Freshness (time since last reindex)
- [ ] Popular Search Filters (bar chart)

### Data Sources Needed:

```promql
# Search metrics
copilot_search_total
copilot_search_success_total
copilot_search_errors_total
copilot_search_latency_avg_ms

# Vector DB metrics
copilot_indexed_messages_total
copilot_qdrant_vectors_count
```

### API Endpoints to Query:

```bash
# Stats endpoint
GET http://localhost:8083/api/stats
```

---

## 6. System Health Dashboard ⬜

**File:** `system-health.json`  
**Status:** TODO  
**Priority:** P2

### Required Panels:

- [ ] Service Status Overview (status map)
- [ ] Container CPU Usage (time series per container)
- [ ] Container Memory Usage (time series per container)
- [ ] Disk Usage for Backups (gauge)
- [ ] Network I/O (time series)
- [ ] Prometheus Scrape Duration (time series)
- [ ] Failed Scrapes (counter)
- [ ] Qdrant Memory Usage (stat)
- [ ] Redis Memory Usage (stat)
- [ ] Redis Hit Rate (gauge)
- [ ] API Response Times (per endpoint - time series)
- [ ] Error Rate by Service (bar chart)
- [ ] Uptime per Service (stat)

### Data Sources Needed:

```promql
# Node exporter metrics
node_cpu_seconds_total
node_memory_MemAvailable_bytes
node_filesystem_avail_bytes

# Container metrics (if cAdvisor added)
container_cpu_usage_seconds_total
container_memory_usage_bytes

# Prometheus self-monitoring
prometheus_tsdb_head_samples_appended_total
up{job="copilot-backup-metrics"}
```

---

## 7. Trends & Forecasting Dashboard ⬜

**File:** `trends-forecasting.json`  
**Status:** TODO  
**Priority:** P2

### Required Panels:

- [ ] 7-Day Session Trend (with prediction line)
- [ ] 30-Day Message Growth (area chart)
- [ ] Monthly Growth Rate (stat with delta)
- [ ] Workspace Activity Trend (multi-line)
- [ ] Predicted Storage Usage (gauge with forecast)
- [ ] Peak Usage Times (heatmap)
- [ ] Session Duration Trends (if available)
- [ ] Comparison: This Week vs Last Week
- [ ] Comparison: This Month vs Last Month
- [ ] Year-over-Year Growth (if data available)
- [ ] Moving Averages (7-day, 30-day)
- [ ] Anomaly Detection Highlights

### PromQL Functions Needed:

```promql
# Rate of change
rate(copilot_sessions_total[7d])

# Prediction (using linear regression)
predict_linear(copilot_sessions_total[30d], 86400 * 7)

# Delta comparison
copilot_sessions_total - copilot_sessions_total offset 7d

# Moving average
avg_over_time(copilot_messages_total[7d])
```

---

## 8. Alerts Dashboard ⬜

**File:** `alerts-dashboard.json`  
**Status:** TODO  
**Priority:** P2

### Required Panels:

- [ ] Active Alerts Count (stat with color)
- [ ] Alert History Table (last 24h)
- [ ] Alert Severity Distribution (pie)
- [ ] Alerts by Service (bar chart)
- [ ] Alert Timeline (annotations on time series)
- [ ] Time to Resolution (if Alertmanager integrated)
- [ ] Most Frequent Alerts (top 10)
- [ ] Alert Silences Active (table)
- [ ] Backup Stale Warning Indicator
- [ ] Search API Error Rate Indicator
- [ ] Qdrant Health Indicator
- [ ] Quick Action Buttons (silence, acknowledge)

### Alert Rules Reference:

```yaml
# From alerting_rules.yml
- BackupStale (>24h since last backup)
- BackupSizeLarge (>5GB)
- SearchAPIHighErrorRate (>5%)
- QdrantDown (service unavailable)
- UnusualSessionGrowth (>50% spike)
- LowMessageCount (<100 messages)
```

---

## 🔧 Implementation Priority

### Phase 1 (Immediate) ✅

1. Main Overview Dashboard
2. Session Explorer Dashboard

### Phase 2 (Next Sprint)

3. Workspace Analytics Dashboard
4. Conversation Insights Dashboard
5. Search Analytics Dashboard

### Phase 3 (Future)

6. System Health Dashboard
7. Trends & Forecasting Dashboard
8. Alerts Dashboard

---

## 📋 Variables Required Across Dashboards

| Variable     | Type     | Query                                                 | Used In                 |
| ------------ | -------- | ----------------------------------------------------- | ----------------------- |
| `$workspace` | Query    | `label_values(copilot_workspace_sessions, workspace)` | All                     |
| `$project`   | Query    | `label_values(copilot_project_sessions, project)`     | Workspace, Conversation |
| `$model`     | Query    | `label_values(copilot_model_usage, model)`            | Conversation            |
| `$timerange` | Interval | `1h, 6h, 12h, 24h, 7d, 30d`                           | Trends                  |
| `$service`   | Custom   | `metrics-exporter, search-api, qdrant, prometheus`    | System Health           |

---

## 🎨 Design Guidelines

### Color Scheme

- **Primary:** Blue (#3274D9)
- **Success:** Green (#73BF69)
- **Warning:** Orange (#FF9830)
- **Error:** Red (#F2495C)
- **Info:** Purple (#B877D9)

### Panel Sizing

- **Stat panels:** 4 units wide, 4 units tall
- **Pie charts:** 8 units wide, 8 units tall
- **Time series:** 12-24 units wide, 8 units tall
- **Tables:** 24 units wide (full width), 10 units tall

### Refresh Intervals

- Real-time dashboards: 10s
- Overview dashboards: 1m
- Analytics dashboards: 5m
- Trends dashboards: 15m

---

## 📝 Notes

1. **Data Retention:** Prometheus is configured for 90-day retention
2. **Scrape Interval:** Metrics are scraped every 15 seconds
3. **Dashboard Provisioning:** All dashboards in `grafana/dashboards/` are auto-loaded
4. **Backup Required:** Export dashboards to JSON before major changes

---

## 🚀 Quick Commands

```bash
# Reload dashboards (after adding new JSON files)
docker compose restart grafana

# Export a dashboard
curl -H "Authorization: Bearer $GRAFANA_API_KEY" \
  http://localhost:3001/api/dashboards/uid/DASHBOARD_UID | jq '.dashboard' > export.json

# Import a dashboard
curl -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -d @dashboard.json http://localhost:3001/api/dashboards/db
```
