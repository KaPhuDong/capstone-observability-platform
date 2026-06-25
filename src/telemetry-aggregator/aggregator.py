"""
TelemetryAggregator: thu thập metrics/logs/traces từ Prometheus/Loki/Tempo.
"""

import logging
from datetime import datetime, timezone
from typing import List

import aiohttp

from config import Settings
from models import TelemetryEvent

logger = logging.getLogger("aggregator")


class TelemetryAggregator:
    """Thu thập telemetry từ Prometheus, Loki, Tempo."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def check_connections(self) -> bool:
        """Kiểm tra kết nối tới Prometheus (health check)."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.settings.prometheus_url}/-/healthy", timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Prometheus connection check failed: {e}")
            return False

    async def get_services(self) -> List[str]:
        """Lấy danh sách services trong namespace target."""
        query = f'kube_deployment_labels{{namespace="{self.settings.target_namespace}"}}'
        data = await self._query_prometheus(query)

        services = set()
        for item in data.get("result", []):
            deployment = item["metric"].get("deployment", "")
            if deployment:
                services.add(deployment)

        return sorted(services)

    async def collect(self, service: str) -> TelemetryEvent:
        """Thu thập telemetry cho 1 service."""
        logger.info(f"Collecting telemetry for {service}...")

        # Metrics
        cpu = await self._get_cpu_usage(service)
        memory = await self._get_memory_usage(service)
        error_rate = await self._get_error_rate(service)
        latency_p95 = await self._get_latency_p95(service)
        latency_p99 = await self._get_latency_p99(service)
        request_rate = await self._get_request_rate(service)
        pod_restarts = await self._get_pod_restarts(service)
        ready_replicas = await self._get_ready_replicas(service)
        desired_replicas = await self._get_desired_replicas(service)

        # Logs
        logs = await self._get_logs(service)

        # Traces
        trace_ids = await self._get_failed_trace_ids(service)

        return TelemetryEvent(
            service=service,
            timestamp=datetime.now(timezone.utc),
            namespace=self.settings.target_namespace,
            cpu_percent=cpu,
            memory_percent=memory,
            error_rate=error_rate,
            latency_p95_ms=latency_p95,
            latency_p99_ms=latency_p99,
            request_rate=request_rate,
            pod_restarts=pod_restarts,
            ready_replicas=ready_replicas,
            desired_replicas=desired_replicas,
            logs=logs,
            trace_ids=trace_ids,
        )

    # ============================================================
    # Prometheus Queries
    # ============================================================
    async def _query_prometheus(self, query: str) -> dict:
        """Execute instant query tới Prometheus."""
        session = await self._get_session()
        url = f"{self.settings.prometheus_url}/api/v1/query"
        try:
            async with session.get(url, params={"query": query}, timeout=10) as resp:
                resp.raise_for_status()
                result = await resp.json()
                return result.get("data", {})
        except Exception as e:
            logger.error(f"Prometheus query failed: {query} | {e}")
            return {"result": []}

    async def _get_cpu_usage(self, service: str) -> float:
        """CPU usage % trung bình của pod."""
        query = (
            f'avg(rate(container_cpu_usage_seconds_total{{'
            f'namespace="{self.settings.target_namespace}",'
            f'pod=~"{service}.*"'
            f'}}[{self.settings.metrics_range}])) * 100'
        )
        data = await self._query_prometheus(query)
        return self._extract_value(data)

    async def _get_memory_usage(self, service: str) -> float:
        """Memory usage %."""
        query = (
            f'avg(container_memory_working_set_bytes{{'
            f'namespace="{self.settings.target_namespace}",'
            f'pod=~"{service}.*"'
            f'}} / container_spec_memory_limit_bytes) * 100'
        )
        data = await self._query_prometheus(query)
        return self._extract_value(data)

    async def _get_error_rate(self, service: str) -> float:
        """Error rate % (5xx / total requests)."""
        query_errors = (
            f'sum(rate(http_server_duration_milliseconds_count{{'
            f'service_name="{service}",'
            f'status_code=~"5.."'
            f'}}[{self.settings.metrics_range}]))'
        )
        query_total = (
            f'sum(rate(http_server_duration_milliseconds_count{{'
            f'service_name="{service}"'
            f'}}[{self.settings.metrics_range}]))'
        )
        errors_data = await self._query_prometheus(query_errors)
        total_data = await self._query_prometheus(query_total)

        errors = self._extract_value(errors_data)
        total = self._extract_value(total_data)
        if total > 0:
            return (errors / total) * 100
        return 0.0

    async def _get_latency_p95(self, service: str) -> float:
        """P95 latency (ms)."""
        query = (
            f'histogram_quantile(0.95, sum(rate(http_server_duration_milliseconds_bucket{{'
            f'service_name="{service}"'
            f'}}[{self.settings.metrics_range}])) by (le))'
        )
        data = await self._query_prometheus(query)
        return self._extract_value(data)

    async def _get_latency_p99(self, service: str) -> float:
        """P99 latency (ms)."""
        query = (
            f'histogram_quantile(0.99, sum(rate(http_server_duration_milliseconds_bucket{{'
            f'service_name="{service}"'
            f'}}[{self.settings.metrics_range}])) by (le))'
        )
        data = await self._query_prometheus(query)
        return self._extract_value(data)

    async def _get_request_rate(self, service: str) -> float:
        """Requests per second."""
        query = (
            f'sum(rate(http_server_duration_milliseconds_count{{'
            f'service_name="{service}"'
            f'}}[{self.settings.metrics_range}]))'
        )
        data = await self._query_prometheus(query)
        return self._extract_value(data)

    async def _get_pod_restarts(self, service: str) -> int:
        """Tổng số restart của pods trong 1h qua."""
        query = (
            f'sum(increase(kube_pod_container_status_restarts_total{{'
            f'namespace="{self.settings.target_namespace}",'
            f'pod=~"{service}.*"'
            f'}}[1h]))'
        )
        data = await self._query_prometheus(query)
        return int(self._extract_value(data))

    async def _get_ready_replicas(self, service: str) -> int:
        """Số pod đang Ready."""
        query = (
            f'sum(kube_deployment_status_replicas_ready{{'
            f'namespace="{self.settings.target_namespace}",'
            f'deployment="{service}"'
            f'}})'
        )
        data = await self._query_prometheus(query)
        return int(self._extract_value(data))

    async def _get_desired_replicas(self, service: str) -> int:
        """Số pod mong muốn."""
        query = (
            f'sum(kube_deployment_spec_replicas{{'
            f'namespace="{self.settings.target_namespace}",'
            f'deployment="{service}"'
            f'}})'
        )
        data = await self._query_prometheus(query)
        return int(self._extract_value(data))

    def _extract_value(self, data: dict) -> float:
        """Lấy giá trị từ Prometheus result."""
        results = data.get("result", [])
        if results:
            value = results[0].get("value", [None, 0])[1]
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    # ============================================================
    # Loki Queries
    # ============================================================
    async def _get_logs(self, service: str) -> List[str]:
        """Lấy sample logs từ Loki (ERROR/WARN level)."""
        session = await self._get_session()
        url = f"{self.settings.loki_url}/loki/api/v1/query_range"
        logql = f'{{namespace="{self.settings.target_namespace}", pod=~"{service}.*"}} |~ "(?i)(error|warn|exception|timeout|fail)"'

        params = {
            "query": logql,
            "limit": self.settings.logs_limit,
        }

        try:
            async with session.get(url, params=params, timeout=10) as resp:
                resp.raise_for_status()
                result = await resp.json()
                logs = []
                for stream in result.get("data", {}).get("result", []):
                    for entry in stream.get("values", []):
                        log_line = entry[1]  # [timestamp, log_text]
                        logs.append(log_line)
                return logs[:self.settings.logs_limit]
        except Exception as e:
            logger.error(f"Loki query failed: {e}")
            return []

    # ============================================================
    # Tempo Queries
    # ============================================================
    async def _get_failed_trace_ids(self, service: str) -> List[str]:
        """Lấy trace IDs của các request bị lỗi từ Tempo."""
        # Tempo search API (cần enable search feature)
        # Thường sẽ query qua Grafana hoặc dùng TraceQL
        # Để đơn giản, ta sẽ lấy trace_ids từ metrics span_status=error
        query = (
            f'topk(10, sum by (trace_id) (rate(span_status{{'
            f'service_name="{service}",'
            f'status_code="error"'
            f'}}[{self.settings.metrics_range}])))'
        )
        # Note: query này giả định Tempo export metrics về span
        # Thực tế cần check Tempo API docs hoặc dùng Grafana Explore
        return []  # Placeholder
