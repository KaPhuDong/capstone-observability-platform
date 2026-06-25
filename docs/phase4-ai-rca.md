# Phase 4: AI RCA Engine

Mục tiêu: AI phân tích telemetry event và đưa ra Root Cause Analysis (RCA) + Recommendation.

## RCA Flow

```
TelemetryEvent
      │
      ▼
AI Endpoint (OpenAI / Ollama / Azure)
      │
      ▼
{
  "root_cause": "paymentservice unavailable",
  "confidence": 0.92,
  "recommendation": "restart deployment paymentservice",
  "severity": "critical",
  "affected_services": ["checkoutservice", "paymentservice"],
  "kubectl_commands": [
    "kubectl rollout restart deployment/paymentservice -n otel-demo"
  ]
}
```

## AI Endpoint Options

### Option A: OpenAI (mặc định)
```bash
kubectl create secret generic ai-gateway-secrets \
  --from-literal=ai-endpoint-url="https://api.openai.com/v1/chat/completions" \
  --from-literal=ai-api-key="sk-..." \
  -n ai-gateway
```

Model: `gpt-4o-mini` (cost-effective) hoặc `gpt-4o`

### Option B: Azure OpenAI
```bash
kubectl create secret generic ai-gateway-secrets \
  --from-literal=ai-endpoint-url="https://YOUR_RESOURCE.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-01" \
  --from-literal=ai-api-key="..." \
  -n ai-gateway
```

### Option C: Ollama (local, không mất phí)
```bash
# Deploy Ollama trong cluster
kubectl apply -f kubernetes/ai-gateway/ollama-deployment.yaml

kubectl create secret generic ai-gateway-secrets \
  --from-literal=ai-endpoint-url="http://ollama.ai-gateway.svc.cluster.local:11434/api/chat" \
  --from-literal=ai-api-key="none" \
  -n ai-gateway
```

## System Prompt

AI nhận context:
```
Bạn là SRE chuyên gia. Phân tích telemetry data và xác định root cause.
Input: metrics (CPU/Memory/Error Rate/Latency), logs (error lines), traces (failed trace IDs)
Output: JSON với root_cause, confidence, recommendation, kubectl_commands
```

## Ví dụ RCA Results

### Scenario: Payment Service Down

**Input Telemetry**:
```json
{
  "service": "checkoutservice",
  "error_rate": 100.0,
  "latency_p95_ms": 30000,
  "ready_replicas": 1,
  "desired_replicas": 1,
  "logs": ["timeout calling paymentservice: dial tcp: connection refused"],
  "trace_ids": ["abc123"]
}
```

**AI Output**:
```json
{
  "root_cause": "paymentservice is unavailable - all checkout requests failing with connection refused error when attempting to reach payment endpoint",
  "confidence": 0.95,
  "recommendation": "Restart paymentservice deployment and investigate pod logs for startup errors",
  "severity": "critical",
  "affected_services": ["checkoutservice", "paymentservice"],
  "analysis_summary": "100% error rate with connection refused logs strongly indicates paymentservice is down. The checkout service is healthy but cannot complete transactions without payment processing.",
  "kubectl_commands": [
    "kubectl get pods -n otel-demo | grep payment",
    "kubectl describe deployment paymentservice -n otel-demo",
    "kubectl rollout restart deployment/paymentservice -n otel-demo",
    "kubectl logs -f deployment/paymentservice -n otel-demo"
  ]
}
```

### Scenario: High CPU (Resource Stress)

**Input Telemetry**:
```json
{
  "service": "recommendationservice",
  "cpu_percent": 95.0,
  "memory_percent": 88.0,
  "pod_restarts": 5,
  "error_rate": 25.0,
  "logs": ["OOMKilled", "memory limit exceeded"]
}
```

**AI Output**:
```json
{
  "root_cause": "recommendationservice is experiencing OOM kills due to insufficient memory limits (88% memory usage, 5 restarts in last hour)",
  "confidence": 0.88,
  "recommendation": "Increase memory limits for recommendationservice from current setting to at least 512Mi",
  "severity": "high",
  "affected_services": ["recommendationservice", "frontend"],
  "kubectl_commands": [
    "kubectl top pod -n otel-demo | grep recommendation",
    "kubectl patch deployment recommendationservice -n otel-demo --type=json -p='[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/resources/limits/memory\",\"value\":\"512Mi\"}]'"
  ]
}
```

## Tích hợp Alerting

Có thể mở rộng AI Gateway để gửi RCA kết quả về:
- Slack / Teams webhook
- PagerDuty
- Email
- Grafana annotation

Xem thêm: [Alerting Integration](adr/alerting-integration.md)

## Giới hạn và Cải tiến

| Limitation | Cải tiến |
|-----------|---------|
| AI không biết lịch sử | Lưu RCA history vào PostgreSQL |
| Phân tích 1 service tại 1 thời điểm | Correlation analysis đa service |
| Không tự hành động | Auto-remediation với Kubernetes operator |
| Phụ thuộc OpenAI | Fine-tuned model với data từ hệ thống của bạn |
