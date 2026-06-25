#!/bin/bash
# ============================================================
# Phase 2: Fault Injection Scripts
# Giả lập lỗi để trigger anomaly signals
# ============================================================

set -euo pipefail

NAMESPACE="${NAMESPACE:-otel-demo}"
SLEEP_AFTER="${SLEEP_AFTER:-60}"  # seconds to observe after fault

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

usage() {
  cat <<EOF
Usage: $0 <command> [service]

Commands:
  kill-pod <service>          - Xóa 1 pod của service (simulate crash)
  scale-down <service>        - Scale xuống 0 (simulate outage)
  scale-up <service>          - Scale lên lại 1 (restore)
  resource-stress <service>   - Inject CPU/Memory stress
  list                        - Liệt kê tất cả deployments trong namespace
  status                      - Xem trạng thái tất cả services

Examples:
  $0 kill-pod checkoutservice
  $0 scale-down paymentservice
  $0 scale-up paymentservice
  $0 list
EOF
}

list_services() {
  log_info "Deployments trong namespace '$NAMESPACE':"
  kubectl get deployments -n "$NAMESPACE" -o wide
}

get_status() {
  log_info "Status của tất cả services trong '$NAMESPACE':"
  kubectl get pods -n "$NAMESPACE" -o wide
  echo ""
  kubectl top pods -n "$NAMESPACE" 2>/dev/null || log_warn "kubectl top yêu cầu metrics-server"
}

kill_pod() {
  local service="$1"
  log_warn "Killing pod của $service trong $NAMESPACE..."
  
  POD=$(kubectl get pod -n "$NAMESPACE" -l "app.kubernetes.io/name=$service" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  
  if [ -z "$POD" ]; then
    # Thử label khác
    POD=$(kubectl get pod -n "$NAMESPACE" \
      -o jsonpath="{.items[?(@.metadata.name contains '$service')].metadata.name}" 2>/dev/null || true)
  fi

  if [ -z "$POD" ]; then
    log_error "Không tìm thấy pod cho service: $service"
    kubectl get pods -n "$NAMESPACE" | grep "$service" || true
    exit 1
  fi

  log_warn "Deleting pod: $POD"
  kubectl delete pod "$POD" -n "$NAMESPACE"
  
  log_info "Pod đã bị xóa. Kubernetes sẽ tự động tạo lại."
  log_info "Quan sát events trong $SLEEP_AFTER giây..."
  sleep "$SLEEP_AFTER"
  
  log_info "Trạng thái sau fault injection:"
  kubectl get pods -n "$NAMESPACE" | grep "$service" || true
}

scale_down() {
  local service="$1"
  log_error "Scaling DOWN $service xuống 0 replicas (simulate OUTAGE)..."
  
  kubectl scale deployment "$service" \
    --replicas=0 \
    -n "$NAMESPACE"
  
  log_info "Service $service đã bị tắt."
  log_info "Các service phụ thuộc sẽ bắt đầu báo lỗi..."
  log_warn "Chạy '$0 scale-up $service' để khôi phục"
}

scale_up() {
  local service="$1"
  local replicas="${REPLICAS:-1}"
  
  log_info "Scaling UP $service lên $replicas replica(s)..."
  
  kubectl scale deployment "$service" \
    --replicas="$replicas" \
    -n "$NAMESPACE"
  
  log_info "Đang chờ service khởi động..."
  kubectl rollout status deployment/"$service" \
    -n "$NAMESPACE" \
    --timeout=120s
  
  log_info "Service $service đã được khôi phục."
}

resource_stress() {
  local service="$1"
  log_warn "Resource stress injection cho $service (patch limits)..."
  
  # Patch resource limits để tạo memory pressure
  kubectl patch deployment "$service" \
    -n "$NAMESPACE" \
    --type=json \
    -p='[
      {
        "op": "replace",
        "path": "/spec/template/spec/containers/0/resources/limits/memory",
        "value": "64Mi"
      }
    ]'
  
  log_warn "Memory limit đã giảm xuống 64Mi. Service sẽ bị OOMKill."
  log_warn "Chạy '$0 scale-up $service' để restore"
}

# ============================================================
# Main
# ============================================================
if [ $# -eq 0 ]; then
  usage
  exit 1
fi

COMMAND="$1"
SERVICE="${2:-}"

case "$COMMAND" in
  kill-pod)
    [ -z "$SERVICE" ] && { log_error "Cần tên service"; usage; exit 1; }
    kill_pod "$SERVICE"
    ;;
  scale-down)
    [ -z "$SERVICE" ] && { log_error "Cần tên service"; usage; exit 1; }
    scale_down "$SERVICE"
    ;;
  scale-up)
    [ -z "$SERVICE" ] && { log_error "Cần tên service"; usage; exit 1; }
    scale_up "$SERVICE"
    ;;
  resource-stress)
    [ -z "$SERVICE" ] && { log_error "Cần tên service"; usage; exit 1; }
    resource_stress "$SERVICE"
    ;;
  list)
    list_services
    ;;
  status)
    get_status
    ;;
  *)
    log_error "Lệnh không hợp lệ: $COMMAND"
    usage
    exit 1
    ;;
esac
