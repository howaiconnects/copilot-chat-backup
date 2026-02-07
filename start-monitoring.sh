#!/bin/bash
# =============================================================================
# Copilot Chat Backup - Monitoring Stack Manager
# =============================================================================
# Usage:
#   ./start-monitoring.sh          # Start all services
#   ./start-monitoring.sh stop     # Stop all services
#   ./start-monitoring.sh restart  # Restart all services
#   ./start-monitoring.sh status   # Check status
#   ./start-monitoring.sh logs     # View logs
#   ./start-monitoring.sh build    # Rebuild images
#   ./start-monitoring.sh clean    # Stop and remove volumes
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITORING_DIR="$SCRIPT_DIR/monitoring"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║     🚀 Copilot Chat Backup - Monitoring Stack Manager        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running. Please start Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
}

get_compose_cmd() {
    if docker compose version &> /dev/null 2>&1; then
        echo "docker compose"
    else
        echo "docker-compose"
    fi
}

start_services() {
    print_header
    echo "Starting monitoring stack..."
    echo ""
    
    check_docker
    
    cd "$MONITORING_DIR"
    
    COMPOSE_CMD=$(get_compose_cmd)
    
    # Build images if needed
    print_status "Building custom images..."
    $COMPOSE_CMD build --quiet
    
    # Start services
    print_status "Starting services..."
    $COMPOSE_CMD up -d
    
    echo ""
    echo "Waiting for services to be ready..."
    sleep 5
    
    # Check service health
    echo ""
    echo -e "${BLUE}Service Status:${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    check_service "Prometheus" "http://localhost:9091/-/ready" "9091"
    check_service "Grafana" "http://localhost:3001/api/health" "3001"
    check_service "Metrics Exporter" "http://localhost:8082/api/health" "8082"
    check_service "Search API" "http://localhost:8083/health" "8083"
    check_service "Qdrant" "http://localhost:6337/health" "6337"
    check_service "Redis" "" "6390"
    
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Monitoring stack is ready!${NC}"
    echo ""
    echo "Access points:"
    echo "  📊 Grafana:        http://localhost:3001  (admin/copilot-admin-2024)"
    echo "  📈 Prometheus:     http://localhost:9091"
    echo "  📉 Metrics API:    http://localhost:8082"
    echo "  🔍 Search API:     http://localhost:8083"
    echo "  🗄️  Qdrant:         http://localhost:6337/dashboard"
    echo ""
}

check_service() {
    local name=$1
    local url=$2
    local port=$3
    
    # Check if port is listening
    if nc -z localhost $port 2>/dev/null; then
        if [ -n "$url" ]; then
            # Try to hit the health endpoint
            if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q "200"; then
                echo -e "  ${GREEN}●${NC} $name (port $port) - ${GREEN}healthy${NC}"
            else
                echo -e "  ${YELLOW}●${NC} $name (port $port) - ${YELLOW}starting${NC}"
            fi
        else
            echo -e "  ${GREEN}●${NC} $name (port $port) - ${GREEN}running${NC}"
        fi
    else
        echo -e "  ${RED}●${NC} $name (port $port) - ${RED}not running${NC}"
    fi
}

stop_services() {
    print_header
    echo "Stopping monitoring stack..."
    
    check_docker
    cd "$MONITORING_DIR"
    
    COMPOSE_CMD=$(get_compose_cmd)
    $COMPOSE_CMD down
    
    print_status "All services stopped."
}

restart_services() {
    stop_services
    echo ""
    start_services
}

show_status() {
    print_header
    echo "Checking service status..."
    echo ""
    
    check_docker
    cd "$MONITORING_DIR"
    
    COMPOSE_CMD=$(get_compose_cmd)
    $COMPOSE_CMD ps
    
    echo ""
    echo -e "${BLUE}Health Checks:${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    check_service "Prometheus" "http://localhost:9091/-/ready" "9091"
    check_service "Grafana" "http://localhost:3001/api/health" "3001"
    check_service "Metrics Exporter" "http://localhost:8082/api/health" "8082"
    check_service "Search API" "http://localhost:8083/health" "8083"
    check_service "Qdrant" "http://localhost:6337/health" "6337"
    check_service "Redis" "" "6390"
}

show_logs() {
    check_docker
    cd "$MONITORING_DIR"
    
    COMPOSE_CMD=$(get_compose_cmd)
    
    if [ -n "$2" ]; then
        $COMPOSE_CMD logs -f "$2"
    else
        $COMPOSE_CMD logs -f
    fi
}

build_images() {
    print_header
    echo "Building custom images..."
    
    check_docker
    cd "$MONITORING_DIR"
    
    COMPOSE_CMD=$(get_compose_cmd)
    $COMPOSE_CMD build
    
    print_status "Images built successfully."
}

clean_all() {
    print_header
    print_warning "This will stop all services and remove all data volumes!"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        check_docker
        cd "$MONITORING_DIR"
        
        COMPOSE_CMD=$(get_compose_cmd)
        $COMPOSE_CMD down -v
        
        print_status "All services stopped and volumes removed."
    else
        echo "Cancelled."
    fi
}

show_help() {
    print_header
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start    Start all monitoring services (default)"
    echo "  stop     Stop all services"
    echo "  restart  Restart all services"
    echo "  status   Show service status"
    echo "  logs     View service logs (optional: service name)"
    echo "  build    Rebuild Docker images"
    echo "  clean    Stop services and remove volumes"
    echo "  help     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                  # Start all services"
    echo "  $0 logs grafana     # View Grafana logs only"
    echo "  $0 restart          # Restart everything"
}

# Main
case "${1:-start}" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "$@"
        ;;
    build)
        build_images
        ;;
    clean)
        clean_all
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
