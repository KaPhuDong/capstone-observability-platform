# Phase 3: Telemetry Aggregator

Mục tiêu: Xây dựng service thu thập Metrics/Logs/Traces, gom thành 1 event, gửi AI API.

## Kiến trúc

```
Prometheus ─┐
Loki       ─┼──► Telemetry Aggregator ──► AI API
Tempo      ─┘         │
                       ▼
              TelemetryEvent JSON
```

## TelemetryEvent Payload

```json
{
  "service": "checkoutservice",
  "timestamp": "2026-06-25T10:00:00Z",
  "namespace": "otel-demo",
  "cpu_percent": 89.0,
  "memory_percent": 72.0,
  "error_rate": 15.4,
  "latency_p95_ms": 2300,
  "latency_p99_ms": 3100,
  "request_rate": 45.2,
  "pod_restarts": 3,
  "ready_replicas": 0,
  "desired_replicas": 1,
  "logs": [
    "timeout calling paymentservice: context deadline exceeded",
    "failed to process payment: connection refused"
  ],
  "trace_ids": [
    "abc123def456",
    "xyz789uvw012"
  ]
}
```

## Deploy Telemetry Aggregator

### 1. Build Docker image

```bash
cd src/telemetry-aggregator/

docker build -t capstone/telemetry-aggregator:latest .

# Push tới registry (ECR hoặc DockerHub)
docker push your-registry/telemetry-aggregator:latest
```

### 2. Cấu hình AI API Key

```bash
kubectl create secret generic ai-gateway-secrets \
  --from-literal=ai-endpoint-url="https://api.openai.com/v1/chat/completions" \
  --from-literal=ai-api-key="sk-your-key-here" \
  -n ai-gateway
```

### 3. Deploy

```bash
kubectl apply -f kubernetes/ai-gateway/namespace.yaml
kubectl apply -f kubernetes/ai-gateway/deployment.yaml

# Kiểm tra
kubectl get pods -n ai-gateway
kubectl logs -f deployment/telemetry-aggregator -n ai-gateway
```

### 4. Test thủ công

```bash
# Port-forward API
kubectl port-forward svc/telemetry-aggregator 8080:8080 -n ai-gateway

# Health check
curl http://localhost:8080/health

# Trigger analysis ngay lập tức
curl -X POST http://localhost:8080/analyze/trigger

# Phân tích 1 service cụ thể
curl http://localhost:8080/analyze/service/checkoutservice
```

## Cấu hình Thresholds

Chỉnh trong `kubernetes/ai-gateway/deployment.yaml`:

```yaml
env:
  - name: POLL_INTERVAL_SECONDS
    value: "60"              # Check mỗi 60 giây
  - name: ERROR_RATE_THRESHOLD
    value: "5.0"             # Gửi AI khi error_rate > 5%
  - name: LATENCY_P95_THRESHOLD_MS
    value: "2000"            # Gửi AI khi p95 > 2000ms
  - name: CPU_THRESHOLD_PERCENT
    value: "80"              # Gửi AI khi CPU > 80%
  - name: MEMORY_THRESHOLD_PERCENT
    value: "80"              # Gửi AI khi Memory > 80%
```

## Kiểm tra Flow

1. Inject fault (Phase 2)
2. Chờ `POLL_INTERVAL_SECONDS`
3. Xem logs:

```bash
kubectl logs -f deployment/telemetry-aggregator -n ai-gateway
```

Output mong đợi:
```
2026-06-25 10:01:00 [INFO] Starting analysis cycle...
2026-06-25 10:01:01 [INFO] Monitoring 8 services: [...]
2026-06-25 10:01:02 [WARNING] Anomaly detected in checkoutservice: error_rate=15.4%, latency_p95=2300ms
2026-06-25 10:01:03 [INFO] Sending telemetry event for checkoutservice to AI...
2026-06-25 10:01:05 [WARNING] [RCA] service=checkoutservice | root_cause='paymentservice unavailable' | confidence=92% | recommendation='restart deployment paymentservice'
```

## Next Steps

➡️ [Phase 4: AI RCA Engine](phase4-ai-rca.md)
