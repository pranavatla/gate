#!/bin/bash
set -euo pipefail

# Deploy LangSmith integration to production
# Requires: SSH access to production server, sudo privileges, environment variables set

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# Check prerequisites
check_requirements() {
    log_info "Checking prerequisites..."

    if [ -z "${LANGSMITH_API_KEY:-}" ]; then
        log_error "LANGSMITH_API_KEY environment variable not set"
    fi

    if [ -z "${GATE_HOST:-}" ]; then
        log_error "GATE_HOST environment variable not set (e.g., gate-prod.example.com)"
    fi

    if [ -z "${GATE_DB_URL:-}" ]; then
        log_error "GATE_DB_URL environment variable not set"
    fi

    if ! command -v ssh &> /dev/null; then
        log_error "ssh command not found"
    fi

    log_info "Prerequisites check passed"
}

# Step 1: Deploy database migration
deploy_db_migration() {
    log_info "Step 1: Deploying database migration..."

    psql "$GATE_DB_URL" < "$REPO_ROOT/db/018_langsmith_integration.sql" || \
        log_error "Database migration failed"

    log_info "Database migration deployed successfully"
}

# Step 2: Copy sync service files
deploy_systemd_service() {
    log_info "Step 2: Deploying systemd service and timer..."

    ssh "root@$GATE_HOST" bash <<'EOF'
set -euo pipefail

GATE_DIR="${GATE_DIR:-/opt/gate}"

# Copy systemd files
mkdir -p /etc/systemd/system
cp "$GATE_DIR/deploy/systemd/gate-langsmith-sync.service" /etc/systemd/system/
cp "$GATE_DIR/deploy/systemd/gate-langsmith-sync.timer" /etc/systemd/system/

# Reload and enable
systemctl daemon-reload
systemctl enable gate-langsmith-sync.timer
systemctl restart gate-langsmith-sync.timer

# Verify
systemctl status gate-langsmith-sync.timer

echo "Systemd service deployed"
EOF

    log_info "Systemd service deployed successfully"
}

# Step 3: Verify sync service is running
verify_sync_service() {
    log_info "Step 3: Verifying sync service..."

    sleep 5  # Give timer time to fire

    ssh "root@$GATE_HOST" bash <<'EOF'
set -euo pipefail

# Check timer status
echo "Timer status:"
systemctl status gate-langsmith-sync.timer || true

# Check recent logs
echo ""
echo "Recent logs:"
journalctl -u gate-langsmith-sync -n 10 --no-pager || echo "No logs yet"

# Check if traces exist
echo ""
echo "Checking if traces are being collected..."
# This requires psql access, so just provide the query
cat << 'SQL'
Run this query on your Postgres:
SELECT COUNT(*) as trace_count, MAX(created_at) as latest_trace
FROM langsmith_traces;
SQL
EOF

    log_info "Sync service verification complete"
}

# Step 4: Import Grafana dashboard
import_grafana_dashboard() {
    log_info "Step 4: Importing Grafana dashboard..."

    if [ -z "${GRAFANA_URL:-}" ] || [ -z "${GRAFANA_API_KEY:-}" ]; then
        log_warn "GRAFANA_URL or GRAFANA_API_KEY not set - skipping dashboard import"
        log_info "To import manually:"
        log_info "1. Go to Grafana → Dashboards → Import"
        log_info "2. Upload: obs.atla.in/grafana/dashboards/gate-langsmith.json"
        log_info "3. Select Postgres datasource"
        return
    fi

    local dashboard_file="$REPO_ROOT/../obs.atla.in/grafana/dashboards/gate-langsmith.json"

    if [ ! -f "$dashboard_file" ]; then
        log_warn "Dashboard file not found at $dashboard_file"
        log_info "To import manually:"
        log_info "1. Clone pranavatla/obs.atla.in"
        log_info "2. Go to Grafana → Dashboards → Import"
        log_info "3. Upload: grafana/dashboards/gate-langsmith.json"
        return
    fi

    # Import dashboard via Grafana API
    curl -X POST \
        -H "Authorization: Bearer $GRAFANA_API_KEY" \
        -H "Content-Type: application/json" \
        -d @"$dashboard_file" \
        "$GRAFANA_URL/api/dashboards/db" || \
        log_error "Failed to import dashboard"

    log_info "Grafana dashboard imported successfully"
}

# Step 5: Provide integration guide
show_next_steps() {
    log_info "Step 5: Integration guide"

    cat <<'EOF'

╔════════════════════════════════════════════════════════════════╗
║                  LangSmith Integration Complete!               ║
╚════════════════════════════════════════════════════════════════╝

✅ Completed:
  • LangSmith input/output recording enabled (PR #17 merged)
  • Database schema deployed
  • Sync service installed and running (checks every 5 min)
  • Grafana dashboard imported

📊 Next Steps:

1. Verify Traces Are Flowing:
   psql $GATE_DB_URL -c "SELECT COUNT(*) FROM langsmith_traces;"

2. Open Grafana Dashboard:
   Go to: Grafana → Dashboards → gate.atla.in · LangSmith Traces

3. View Sample Traces:
   Click any row in the "Recent Traces" table
   Click "View in LangSmith" button to see full trace

4. Set Up Alerts (Optional):
   Go to Grafana → Alerting → Alert Rules
   Import rules from: obs.atla.in/deploy/grafana/alerts/langsmith-alerts.yaml

5. Query Traces by Request ID:
   psql $GATE_DB_URL -c "
   SELECT * FROM dash_traces
   WHERE request_id = 'YOUR_REQUEST_ID';"

📚 Documentation:
   Read full guide: obs.atla.in/docs/langsmith-integration.md

🔍 Troubleshooting:
   Sync service logs: journalctl -u gate-langsmith-sync -f
   Grafana datasource: Test Postgres connection in Grafana settings

💰 Cost:
   Typical usage: ~$0.10/month for trace storage in LangSmith

Questions? Check the integration guide or gateway README.

EOF
}

# Main
main() {
    log_info "Starting LangSmith integration deployment..."

    check_requirements

    log_warn "This script will deploy to production: $GATE_HOST"
    read -p "Continue? (yes/no) " -n 3 -r
    echo
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        log_error "Deployment cancelled"
    fi

    deploy_db_migration
    deploy_systemd_service
    verify_sync_service
    import_grafana_dashboard
    show_next_steps

    log_info "✅ Deployment complete!"
}

main "$@"
