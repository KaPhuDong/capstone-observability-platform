# Phase 2: Fault Injection

Mục tiêu: Giả lập lỗi trong OTel Demo để tạo anomaly signals (error_rate tăng, latency cao, pod restarts).

## Fault Types

| Fault | Hiện tượng | Metric / Log / Trace |
|-------|-----------|----------------------|
| Kill Pod | Pod restart, connection refused | `kube_pod_container_status_restarts_total`, logs: "connection refused" |
| Scale Down | Service outage | Error rate = 100%, logs: "timeout", traces: all spans fail |
| Resource Stress | OOMKill | Memory usage → 100%, pod restart |
| Network Delay | High latency | P95/P99 latency tăng vọt |

## Prerequisites

```bash
# Cài kubectl
kubectl version --client

# Script injection
chmod +x scripts/fault-injection/inject-fault.sh
```

## Scenario 1: Kill Payment Service Pod

```bash
# List services
./scripts/fault-injection/inject-fault.sh list

# Kill 1 pod
./scripts/fault-injection/inject-fault.sh kill-pod paymentservice

# Quan sát:
# - Grafana: error_rate tăng trong checkoutservice
# - Logs: "timeout calling paymentservice"
# - Traces: spans từ checkout → payment bị fail
```

**Kết quả mong đợi**:
- `error_rate`: 0% → 10-20% (tạm thời trong vài giây)
- `latency_p95`: tăng khi timeout
- Logs có dòng: `"error calling paymentservice: connection refused"`

## Scenario 2: Scale Down Payment Service

```bash
# Scale xuống 0 (simulate full outage)
./scripts/fault-injection/inject-fault.sh scale-down paymentservice

# Quan sát trong 1-2 phút:
# - checkoutservice báo lỗi liên tục
# - Error rate = 100%
# - Traces: tất cả request checkout đều fail

# Khôi phục
./scripts/fault-injection/inject-fault.sh scale-up paymentservice
```

**Kết quả mong đợi**:
- `error_rate`: 100% (toàn bộ checkout requests fail)
- `ready_replicas`: 0/1
- Logs: `"paymentservice unavailable"`
- Traces: span `checkout → payment` có status `error`

## Scenario 3: Resource Stress (OOMKill)

```bash
# Giảm memory limit xuống 64Mi
./scripts/fault-injection/inject-fault.sh resource-stress checkoutservice

# Pod sẽ bị OOMKill và restart liên tục

# Khôi phục
kubectl rollout undo deployment/checkoutservice -n otel-demo
```

**Kết quả mong đợi**:
- `memory_percent`: → 100%
- `pod_restarts`: tăng
- Logs: `"OOMKilled"`

## Verify Telemetry Changes

### Prometheus (Metrics)
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```

Truy cập: http://localhost:9090

Queries:
```promql
# Error rate
sum(rate(http_server_duration_milliseconds_count{status_code=~"5.."}[5m])) by (service_name) 
/ 
sum(rate(http_server_duration_milliseconds_count[5m])) by (service_name)

# P95 latency
histogram_quantile(0.95, sum(rate(http_server_duration_milliseconds_bucket[5m])) by (le, service_name))

# Pod restarts
increase(kube_pod_container_status_restarts_total{namespace="otel-demo"}[1h])
```

### Loki (Logs)
```bash
kubectl port-forward -n monitoring svc/loki-gateway 3100:80
```

Query (qua Grafana Explore):
```logql
{namespace="otel-demo", pod=~"checkoutservice.*"} |~ "(?i)(error|timeout|fail)"
```

### Tempo (Traces)
Grafana → Explore → Tempo → Search

Filter:
- Service: `checkoutservice`
- Status: `error`
- Duration: `> 2s`

## Cleanup

Khôi phục tất cả services về trạng thái ban đầu:

```bash
kubectl rollout restart deployment -n otel-demo
```

## Next Steps

➡️ [Phase 3: Telemetry Aggregator](phase3-telemetry-aggregator.md)
