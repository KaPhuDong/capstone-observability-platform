"""
Telemetry Aggregator - Phase 3
Thu thập Metrics/Logs/Traces từ Prometheus/Loki/Tempo,
gom thành 1 TelemetryEvent, gửi đến AI API để phân tích RCA.
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse

from aggregator import TelemetryAggregator
from ai_client import AIClient
from models import TelemetryEvent, RCAResult
from config import Settings

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("telemetry-aggregator")

# ============================================================
# App setup
# ============================================================
settings = Settings()
app = FastAPI(
    title="Telemetry Aggregator",
    description="Collects telemetry from Prometheus/Loki/Tempo and sends to AI for RCA",
    version="1.0.0",
)

aggregator = TelemetryAggregator(settings)
ai_client = AIClient(settings)

# Background polling task handle
_polling_task: asyncio.Task | None = None


# ============================================================
# Lifecycle
# ============================================================
@app.on_event("startup")
async def startup():
    logger.info("Starting Telemetry Aggregator...")
    logger.info(f"Prometheus: {settings.prometheus_url}")
    logger.info(f"Loki: {settings.loki_url}")
    logger.info(f"Tempo: {settings.tempo_url}")
    logger.info(f"AI Endpoint: {settings.ai_endpoint_url}")
    logger.info(f"Poll interval: {settings.poll_interval_seconds}s")

    global _polling_task
    _polling_task = asyncio.create_task(polling_loop())
    logger.info("Polling loop started.")


@app.on_event("shutdown")
async def shutdown():
    global _polling_task
    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
    logger.info("Telemetry Aggregator stopped.")


# ============================================================
# Polling loop
# ============================================================
async def polling_loop():
    """Vòng lặp chính: cứ mỗi POLL_INTERVAL_SECONDS, thu thập telemetry và gửi AI."""
    while True:
        try:
            await run_analysis_cycle()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in polling loop: {e}", exc_info=True)
        await asyncio.sleep(settings.poll_interval_seconds)


async def run_analysis_cycle():
    """1 chu kỳ phân tích: thu thập → gom event → gửi AI → log kết quả."""
    logger.info("Starting analysis cycle...")
    start_time = datetime.now(timezone.utc)

    # Lấy danh sách services cần theo dõi
    services = await aggregator.get_services()
    logger.info(f"Monitoring {len(services)} services: {services}")

    results = []
    for service in services:
        try:
            # Thu thập telemetry cho từng service
            event = await aggregator.collect(service)

            # Chỉ gửi AI nếu có anomaly
            if is_anomaly(event):
                logger.warning(
                    f"Anomaly detected in {service}: "
                    f"error_rate={event.error_rate:.1f}%, "
                    f"latency_p95={event.latency_p95_ms}ms"
                )
                rca = await ai_client.analyze(event)
                log_rca_result(event, rca)
                results.append({"service": service, "event": event.dict(), "rca": rca.dict()})
            else:
                logger.debug(f"Service {service} is healthy, skipping AI analysis.")

        except Exception as e:
            logger.error(f"Failed to process service {service}: {e}", exc_info=True)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(f"Analysis cycle done in {elapsed:.2f}s, {len(results)} anomalies found.")
    return results


def is_anomaly(event: TelemetryEvent) -> bool:
    """Kiểm tra xem có cần phân tích không."""
    return (
        event.error_rate >= settings.error_rate_threshold
        or event.latency_p95_ms >= settings.latency_p95_threshold_ms
        or event.cpu_percent >= settings.cpu_threshold_percent
        or event.memory_percent >= settings.memory_threshold_percent
    )


def log_rca_result(event: TelemetryEvent, rca: RCAResult):
    """Log kết quả RCA."""
    logger.warning(
        f"[RCA] service={event.service} | "
        f"root_cause={rca.root_cause!r} | "
        f"confidence={rca.confidence:.0%} | "
        f"recommendation={rca.recommendation!r}"
    )


# ============================================================
# HTTP API
# ============================================================
@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/ready")
async def ready():
    """Readiness probe: kiểm tra kết nối tới Prometheus."""
    try:
        healthy = await aggregator.check_connections()
        if healthy:
            return {"status": "ready"}
        return JSONResponse(status_code=503, content={"status": "not ready"})
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


@app.post("/analyze/trigger")
async def trigger_analysis(background_tasks: BackgroundTasks):
    """Manually trigger 1 analysis cycle (dùng để test)."""
    background_tasks.add_task(run_analysis_cycle)
    return {"status": "triggered", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/analyze/service/{service_name}")
async def analyze_service(service_name: str):
    """Phân tích 1 service cụ thể ngay lập tức."""
    try:
        event = await aggregator.collect(service_name)
        rca = await ai_client.analyze(event)
        return {
            "event": event.dict(),
            "rca": rca.dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ============================================================
# Entrypoint
# ============================================================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        log_level="info",
    )
