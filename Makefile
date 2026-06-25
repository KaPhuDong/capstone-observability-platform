.PHONY: help init deploy destroy status port-forward logs inject-fault

help: ## Hiển thị help
	@echo "Capstone Observability Platform - Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================
# Phase 1: Setup
# ============================================================
init: ## [Phase 1] Init Terraform và provision EKS
	cd terraform && \
	terraform init && \
	terraform apply -auto-approve
	@echo ""
	@echo "✅ EKS cluster ready. Cấu hình kubectl:"
	@terraform -chdir=terraform output -raw kubeconfig_command

kubeconfig: ## Cấu hình kubectl để truy cập EKS
	@terraform -chdir=terraform output -raw kubeconfig_command | sh

deploy-argocd: ## Deploy ArgoCD
	helm repo add argo https://argoproj.github.io/argo-helm || true
	helm repo update
	helm upgrade --install argocd argo/argo-cd \
		--namespace argocd \
		--create-namespace \
		--values kubernetes/argocd/argocd-values.yaml
	@echo ""
	@echo "✅ ArgoCD deployed. Lấy password:"
	@echo "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"

deploy-apps: ## Deploy App of Apps (OTel Demo + Monitoring stack)
	kubectl apply -f kubernetes/argocd/app-of-apps.yaml
	@echo ""
	@echo "✅ ArgoCD Applications deployed. Xem status:"
	@echo "kubectl get applications -n argocd"

deploy-ai-gateway: ## [Phase 3] Deploy Telemetry Aggregator
	@echo "⚠️  Nhớ set AI API key trước:"
	@echo "kubectl create secret generic ai-gateway-secrets \\"
	@echo "  --from-literal=ai-endpoint-url='https://api.openai.com/v1/chat/completions' \\"
	@echo "  --from-literal=ai-api-key='sk-...' \\"
	@echo "  -n ai-gateway"
	@echo ""
	kubectl apply -f kubernetes/ai-gateway/namespace.yaml
	kubectl apply -f kubernetes/ai-gateway/deployment.yaml

# ============================================================
# Status & Monitoring
# ============================================================
status: ## Xem trạng thái tất cả services
	@echo "=== EKS Nodes ==="
	kubectl get nodes
	@echo ""
	@echo "=== ArgoCD Apps ==="
	kubectl get applications -n argocd
	@echo ""
	@echo "=== OTel Demo Pods ==="
	kubectl get pods -n otel-demo
	@echo ""
	@echo "=== Monitoring Pods ==="
	kubectl get pods -n monitoring
	@echo ""
	@echo "=== AI Gateway Pods ==="
	kubectl get pods -n ai-gateway

port-forward: ## Port-forward Grafana (3000), ArgoCD (8080), OTel Demo (8081)
	@echo "Chạy trong các terminal riêng:"
	@echo ""
	@echo "# Grafana"
	@echo "kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80"
	@echo ""
	@echo "# ArgoCD"
	@echo "kubectl port-forward -n argocd svc/argocd-server 8080:443"
	@echo ""
	@echo "# OTel Demo Frontend"
	@echo "kubectl port-forward -n otel-demo svc/otel-demo-frontend 8081:8080"
	@echo ""
	@echo "# Telemetry Aggregator API"
	@echo "kubectl port-forward -n ai-gateway svc/telemetry-aggregator 8082:8080"

logs: ## Xem logs của Telemetry Aggregator
	kubectl logs -f deployment/telemetry-aggregator -n ai-gateway

# ============================================================
# Phase 2: Fault Injection
# ============================================================
inject-fault: ## [Phase 2] Giả lập lỗi (cần: SERVICE=<service_name> ACTION=<kill-pod|scale-down|scale-up>)
	@if [ -z "$(SERVICE)" ]; then \
		echo "❌ Cần chỉ định SERVICE. Ví dụ:"; \
		echo "make inject-fault SERVICE=paymentservice ACTION=kill-pod"; \
		exit 1; \
	fi
	@if [ -z "$(ACTION)" ]; then \
		echo "❌ Cần chỉ định ACTION: kill-pod, scale-down, scale-up"; \
		exit 1; \
	fi
	bash scripts/fault-injection/inject-fault.sh $(ACTION) $(SERVICE)

list-services: ## List tất cả services trong OTel Demo
	bash scripts/fault-injection/inject-fault.sh list

# ============================================================
# Cleanup
# ============================================================
destroy: ## Xóa EKS cluster (cleanup tất cả)
	@echo "⚠️  Sắp xóa toàn bộ EKS cluster. Bấm Ctrl+C để hủy."
	@sleep 5
	cd terraform && terraform destroy -auto-approve

clean-namespace: ## Xóa namespace otel-demo, monitoring, ai-gateway
	kubectl delete namespace otel-demo --ignore-not-found
	kubectl delete namespace monitoring --ignore-not-found
	kubectl delete namespace ai-gateway --ignore-not-found

# ============================================================
# Development
# ============================================================
build-aggregator: ## Build Docker image cho Telemetry Aggregator
	cd src/telemetry-aggregator && \
	docker build -t capstone/telemetry-aggregator:latest .

push-aggregator: build-aggregator ## Push image lên registry
	@echo "⚠️  Đổi registry URL trong Makefile nếu cần"
	docker tag capstone/telemetry-aggregator:latest \
		YOUR_REGISTRY/telemetry-aggregator:latest
	docker push YOUR_REGISTRY/telemetry-aggregator:latest
