# Capstone Observability Platform

Nền tảng observability end-to-end sử dụng OpenTelemetry Demo trên AWS EKS, tích hợp AI để phân tích Root Cause Analysis (RCA).

## Kiến trúc tổng quan

```
AWS EKS
│
├── OpenTelemetry Demo (nguồn sinh telemetry)
├── OpenTelemetry Collector
├── Prometheus (Metrics)
├── Loki (Logs)
├── Tempo (Traces)
├── Grafana (Visualization)
└── AI Gateway (RCA Engine)
```

## Pipeline

```
Web App (OTel Demo)
        ↓ sinh Metrics + Logs + Traces
OpenTelemetry Collector
        ↓ chuẩn hóa telemetry
Prometheus / Loki / Tempo
        ↓
Telemetry Aggregator
        ↓ gửi event
AI Endpoint
        ↓
Root Cause Analysis + Recommendation
```

## Các giai đoạn triển khai

| Giai đoạn | Mục tiêu | Trạng thái |
|-----------|----------|------------|
| Phase 1 | EKS + OTel Demo + Grafana Stack hoạt động | 🔨 In Progress |
| Phase 2 | Giả lập lỗi, quan sát signal | ⏳ Pending |
| Phase 3 | Telemetry Collector gom event gửi AI | ⏳ Pending |
| Phase 4 | AI phân tích RCA + Recommendation | ⏳ Pending |

## Yêu cầu

- AWS CLI >= 2.x
- Terraform >= 1.5
- kubectl >= 1.28
- Helm >= 3.12
- ArgoCD CLI (tùy chọn)

## Bắt đầu nhanh

```bash
# 1. Provision EKS cluster
cd terraform/
terraform init
terraform apply

# 2. Cấu hình kubectl
aws eks update-kubeconfig --name capstone-obs-cluster --region ap-southeast-1

# 3. Bootstrap ArgoCD
kubectl apply -f kubernetes/argocd/install.yaml
kubectl apply -f kubernetes/argocd/app-of-apps.yaml

# 4. Xem Grafana
kubectl port-forward svc/grafana 3000:80 -n monitoring
# Truy cập: http://localhost:3000 (admin/admin)
```

## Tài liệu chi tiết

- [Phase 1 - Setup EKS & OTel Demo](docs/phase1-setup.md)
- [Phase 2 - Fault Injection](docs/phase2-fault-injection.md)
- [Phase 3 - Telemetry Aggregator](docs/phase3-telemetry-aggregator.md)
- [Phase 4 - AI RCA Engine](docs/phase4-ai-rca.md)
- [Architecture Decision Records](docs/adr/)
