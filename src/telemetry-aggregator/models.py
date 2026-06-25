"""
Data models cho Telemetry Event và RCA Result.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class TelemetryEvent(BaseModel):
    """
    Telemetry event gom từ Prometheus + Loki + Tempo cho 1 service.
    
    Ví dụ payload:
    {
        "service": "checkoutservice",
        "timestamp": "2026-06-25T10:00:00Z",
        "cpu_percent": 89.0,
        "memory_percent": 72.0,
        "error_rate": 15.4,
        "latency_p95_ms": 2300,
        "request_rate": 45.2,
        "logs": ["timeout calling paymentservice"],
        "trace_ids": ["abc123", "xyz456"]
    }
    """
    service: str = Field(..., description="Tên service (ví dụ: checkoutservice)")
    timestamp: datetime = Field(..., description="Thời điểm thu thập telemetry (UTC)")
    namespace: str = Field(default="otel-demo", description="Kubernetes namespace")

    # Metrics
    cpu_percent: float = Field(default=0.0, ge=0, le=100, description="CPU usage %")
    memory_percent: float = Field(default=0.0, ge=0, le=100, description="Memory usage %")
    error_rate: float = Field(default=0.0, ge=0, description="Error rate % (5xx / total)")
    latency_p95_ms: float = Field(default=0.0, ge=0, description="P95 latency (ms)")
    latency_p99_ms: float = Field(default=0.0, ge=0, description="P99 latency (ms)")
    request_rate: float = Field(default=0.0, ge=0, description="Requests per second")
    pod_restarts: int = Field(default=0, ge=0, description="Pod restart count (last hour)")
    ready_replicas: int = Field(default=0, ge=0, description="Số pod đang Ready")
    desired_replicas: int = Field(default=0, ge=0, description="Số pod mong muốn")

    # Logs (sample từ Loki)
    logs: List[str] = Field(default_factory=list, description="Sample log lines (tối đa 10 dòng)")

    # Traces (trace IDs bị lỗi từ Tempo)
    trace_ids: List[str] = Field(default_factory=list, description="Trace IDs của các request lỗi")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class RCAResult(BaseModel):
    """
    Kết quả phân tích Root Cause Analysis từ AI.
    
    Ví dụ:
    {
        "root_cause": "paymentservice unavailable",
        "confidence": 0.92,
        "recommendation": "restart deployment paymentservice",
        "severity": "critical",
        "affected_services": ["checkoutservice", "paymentservice"]
    }
    """
    root_cause: str = Field(..., description="Nguyên nhân gốc rễ được AI xác định")
    confidence: float = Field(..., ge=0, le=1, description="Độ tin cậy (0-1)")
    recommendation: str = Field(..., description="Hành động khắc phục được đề xuất")
    severity: str = Field(
        default="unknown",
        description="Mức độ nghiêm trọng: critical / high / medium / low"
    )
    affected_services: List[str] = Field(
        default_factory=list,
        description="Các service bị ảnh hưởng"
    )
    analysis_summary: Optional[str] = Field(
        default=None,
        description="Phân tích chi tiết từ AI"
    )
    kubectl_commands: List[str] = Field(
        default_factory=list,
        description="Các lệnh kubectl để khắc phục"
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Thời điểm phân tích"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
