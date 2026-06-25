"""
AI Client: gửi TelemetryEvent tới AI API, nhận về RCAResult.
Hỗ trợ OpenAI và các endpoint tương thích (Ollama, Azure OpenAI, v.v.)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from config import Settings
from models import TelemetryEvent, RCAResult

logger = logging.getLogger("ai-client")


# System prompt cho AI
SYSTEM_PROMPT = """You are an expert Site Reliability Engineer (SRE) and DevOps specialist.
You analyze application telemetry data (metrics, logs, traces) to identify root causes of issues.

Given telemetry data from a microservice, you must:
1. Identify the most likely root cause of the issue
2. Assess your confidence level (0.0 to 1.0)
3. Provide a clear, actionable recommendation
4. Identify all affected services
5. Suggest specific kubectl commands if applicable

IMPORTANT: Always respond in valid JSON format with this exact structure:
{
  "root_cause": "<concise description of root cause>",
  "confidence": <float between 0.0 and 1.0>,
  "recommendation": "<specific action to take>",
  "severity": "<critical|high|medium|low>",
  "affected_services": ["<service1>", "<service2>"],
  "analysis_summary": "<detailed analysis>",
  "kubectl_commands": ["<kubectl command 1>", "<kubectl command 2>"]
}"""


def build_user_prompt(event: TelemetryEvent) -> str:
    """Tạo prompt từ TelemetryEvent."""
    # Tính toán các signal bổ sung
    pod_availability = (
        f"{event.ready_replicas}/{event.desired_replicas} replicas ready"
        if event.desired_replicas > 0
        else "unknown"
    )

    logs_section = "\n".join(f"  - {log}" for log in event.logs) if event.logs else "  (no error logs)"
    traces_section = "\n".join(f"  - {tid}" for tid in event.trace_ids[:5]) if event.trace_ids else "  (no failed traces)"

    return f"""Analyze the following telemetry data and identify the root cause:

SERVICE: {event.service}
NAMESPACE: {event.namespace}
TIMESTAMP: {event.timestamp.isoformat()}

METRICS:
  CPU Usage: {event.cpu_percent:.1f}%
  Memory Usage: {event.memory_percent:.1f}%
  Error Rate: {event.error_rate:.1f}%
  P95 Latency: {event.latency_p95_ms:.0f}ms
  P99 Latency: {event.latency_p99_ms:.0f}ms
  Request Rate: {event.request_rate:.1f} req/s
  Pod Availability: {pod_availability}
  Pod Restarts (last 1h): {event.pod_restarts}

ERROR LOGS (sample):
{logs_section}

FAILED TRACE IDs:
{traces_section}

Based on this data, provide a JSON response with root cause analysis and recommendations."""


class AIClient:
    """Client gửi telemetry events tới AI endpoint để phân tích RCA."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.settings.ai_api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self.session

    async def analyze(self, event: TelemetryEvent) -> RCAResult:
        """Gửi telemetry event tới AI và nhận RCA result."""
        prompt = build_user_prompt(event)
        logger.info(f"Sending telemetry event for {event.service} to AI...")

        try:
            response_text = await self._call_openai(prompt)
            rca = self._parse_response(response_text, event)
            rca.timestamp = datetime.now(timezone.utc)
            return rca
        except Exception as e:
            logger.error(f"AI analysis failed: {e}", exc_info=True)
            # Fallback khi AI không respond
            return RCAResult(
                root_cause=f"AI analysis failed: {str(e)}",
                confidence=0.0,
                recommendation="Manual investigation required",
                severity="unknown",
                timestamp=datetime.now(timezone.utc),
            )

    async def _call_openai(self, user_prompt: str) -> str:
        """Gọi OpenAI-compatible API."""
        session = await self._get_session()

        payload = {
            "model": "gpt-4o-mini",  # Thay bằng model phù hợp
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,  # Thấp → deterministic hơn
            "max_tokens": 1000,
            "response_format": {"type": "json_object"},
        }

        async with session.post(
            self.settings.ai_endpoint_url,
            json=payload,
            timeout=30,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_response(self, response_text: str, event: TelemetryEvent) -> RCAResult:
        """Parse JSON response từ AI thành RCAResult."""
        try:
            data = json.loads(response_text)
            return RCAResult(
                root_cause=data.get("root_cause", "Unknown"),
                confidence=float(data.get("confidence", 0.0)),
                recommendation=data.get("recommendation", "No recommendation"),
                severity=data.get("severity", "unknown"),
                affected_services=data.get("affected_services", [event.service]),
                analysis_summary=data.get("analysis_summary"),
                kubectl_commands=data.get("kubectl_commands", []),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse AI response: {e}")
            logger.error(f"Raw response: {response_text}")
            return RCAResult(
                root_cause="Failed to parse AI response",
                confidence=0.0,
                recommendation="Check AI response format",
                severity="unknown",
            )
