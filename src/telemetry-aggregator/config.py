"""
Configuration từ environment variables.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Cấu hình cho Telemetry Aggregator."""

    # Prometheus
    prometheus_url: str = os.getenv(
        "PROMETHEUS_URL",
        "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090",
    )

    # Loki
    loki_url: str = os.getenv(
        "LOKI_URL",
        "http://loki-gateway.monitoring.svc.cluster.local",
    )

    # Tempo
    tempo_url: str = os.getenv(
        "TEMPO_URL",
        "http://tempo.monitoring.svc.cluster.local:3100",
    )

    # AI Endpoint
    ai_endpoint_url: str = os.getenv(
        "AI_ENDPOINT_URL",
        "https://api.openai.com/v1/chat/completions",
    )
    ai_api_key: str = os.getenv("AI_API_KEY", "")

    # Polling
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

    # Anomaly thresholds
    error_rate_threshold: float = float(os.getenv("ERROR_RATE_THRESHOLD", "5.0"))
    latency_p95_threshold_ms: float = float(os.getenv("LATENCY_P95_THRESHOLD_MS", "2000"))
    cpu_threshold_percent: float = float(os.getenv("CPU_THRESHOLD_PERCENT", "80"))
    memory_threshold_percent: float = float(os.getenv("MEMORY_THRESHOLD_PERCENT", "80"))

    # Query timerange
    metrics_range: str = "5m"  # Lấy metrics 5 phút gần nhất
    logs_limit: int = 10  # Lấy tối đa 10 dòng log
    trace_limit: int = 10  # Lấy tối đa 10 trace IDs

    # Target namespace
    target_namespace: str = os.getenv("TARGET_NAMESPACE", "otel-demo")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
