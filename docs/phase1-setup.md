# Phase 1: Setup EKS & OpenTelemetry Demo

Mục tiêu: Triển khai EKS cluster + OTel Demo + Grafana Stack (Prometheus, Loki, Tempo, Grafana).

## Prerequisites

```bash
# AWS CLI v2
aws --version

# Terraform
terraform version

# kubectl
kubectl version --client

# Helm
helm version

# (Optional) ArgoCD CLI
argocd version
```

## Bước 1: Provision EKS Cluster

```bash
cd terraform/

# Copy example vars
cp terraform.tfvars.example terraform.tfvars

# Chỉnh sửa terraform.tfvars nếu cần
# - aws_region
# - cluster_name
# - node_instance_types

# Init & Apply
terraform init
terraform plan
terraform apply -auto-approve
```

**Chờ 10-15 phút** để EKS cluster provisioning xong.

## Bước 2: Cấu hình kubectl

```bash
# Lấy kubeconfig
aws eks update-kubeconfig \
  --name capstone-obs-cluster \
  --region ap-southeast-1

# Kiểm tra
kubectl get nodes
```

## Bước 3: Deploy ArgoCD

```bash
cd ../kubernetes/argocd/

# Cài ArgoCD bằng Helm
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

helm install argocd argo/argo-cd \
  --namespace argocd \
  --create-namespace \
  --values argocd-values.yaml

# Chờ ArgoCD ready
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=argocd-server \
  -n argocd \
  --timeout=300s

# Lấy initial password
ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d)
echo "ArgoCD Admin Password: $ARGOCD_PASSWORD"

# Port-forward để truy cập UI
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Truy cập: `https://localhost:8080`
- Username: `admin`
- Password: `$ARGOCD_PASSWORD`

## Bước 4: Deploy App of Apps

**Lưu ý**: Đổi `repoURL` trong các file YAML sang repo GitHub của bạn.

```bash
# Chỉnh file app-of-apps.yaml
# Thay https://github.com/YOUR_ORG/capstone-observability-platform

# Apply
kubectl apply -f app-of-apps.yaml
```

ArgoCD sẽ tự động:
1. Deploy OTel Demo
2. Deploy Prometheus Stack
3. Deploy Loki + Promtail
4. Deploy Tempo

Xem tiến trình:
```bash
argocd app list
argocd app get otel-demo
```

## Bước 5: Kiểm tra

### OpenTelemetry Demo
```bash
kubectl get pods -n otel-demo
kubectl port-forward -n otel-demo svc/otel-demo-frontend 8081:8080
```
Truy cập: http://localhost:8081

### Grafana
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
```
Truy cập: http://localhost:3000
- Username: `admin`
- Password: `admin123` (hoặc xem trong values.yaml)

Datasources đã được cấu hình tự động:
- **Prometheus**: metrics
- **Loki**: logs
- **Tempo**: traces

### Test Queries

**Prometheus**:
```promql
rate(http_server_duration_milliseconds_count[5m])
```

**Loki**:
```logql
{namespace="otel-demo"} |~ "error|warn"
```

**Tempo**: Vào Explore → chọn Tempo → Search traces

## Bước 6: Verify Data Flow

Kiểm tra xem telemetry đã flow chưa:

```bash
# OTel Collector có export metrics không?
kubectl logs -n otel-demo -l app.kubernetes.io/name=opentelemetry-collector

# Prometheus có scrape được không?
# Truy cập Grafana → Explore → Prometheus
# Query: up{namespace="otel-demo"}

# Loki có logs không?
# Grafana → Explore → Loki
# Query: {namespace="otel-demo"}

# Tempo có traces không?
# Grafana → Explore → Tempo → Search
```

## Troubleshooting

### EKS cluster không tạo được
- Kiểm tra AWS quota: VPC, Elastic IPs, EC2 instances
- Kiểm tra IAM permissions

### ArgoCD không sync
- Kiểm tra `repoURL` đã đúng chưa
- Kiểm tra Helm values có syntax error không

### Grafana không hiển thị data
- Kiểm tra datasources: Configuration → Data sources
- Test connection từng datasource
- Xem logs của Prometheus/Loki/Tempo

### OTel Demo không chạy
```bash
kubectl describe pod -n otel-demo <pod-name>
kubectl logs -n otel-demo <pod-name>
```

## Next Steps

➡️ [Phase 2: Fault Injection](phase2-fault-injection.md)
