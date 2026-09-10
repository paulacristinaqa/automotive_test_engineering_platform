import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TypedDict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiAnalysisRequest, AiLogAnalysis
from atep.ai_engine.schemas import AiLogAnalysisCreate, AiLogAnalysisResponse
from atep.audit.service import record_audit
from atep.core.errors import AiLogAnalysisConflictError, AiLogAnalysisContractError
from atep.events.outbox import enqueue_event

LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\s+"
    r"(?P<level>TRACE|DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\s+"
    r"(?:\[(?P<component>[A-Za-z0-9_.:-]{1,64})\]\s+)?(?P<message>.+)$"
)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
SECRET_PATTERN = re.compile(r"(?i)\b(password|token|secret|api[_-]?key)\s*[:=]\s*\S+")
VIN_PATTERN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
UUID_PATTERN = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")
HEX_PATTERN = re.compile(r"\b0x[0-9a-fA-F]+\b")
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
ALLOWED_TASKS = {"log_analysis", "failure_explanation", "root_cause"}


class LogEventData(TypedDict):
    line_number: int
    timestamp: str
    level: str
    component: str
    message: str
    cluster_id: str


class LogClusterData(TypedDict):
    cluster_id: str
    count: int
    first_timestamp: str
    last_timestamp: str
    levels: list[str]
    representative: str
    line_numbers: list[int]


class LogAnomalyData(TypedDict):
    anomaly_type: str
    severity: str
    cluster_id: str
    explanation: str
    line_numbers: list[int]


def _sanitize(message: str) -> str:
    value = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", message)
    value = BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    value = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    value = VIN_PATTERN.sub("[VIN_REDACTED]", value)
    return value[:1000]


def _cluster_id(message: str) -> str:
    normalized = UUID_PATTERN.sub("<uuid>", message.lower())
    normalized = HEX_PATTERN.sub("<hex>", normalized)
    normalized = NUMBER_PATTERN.sub("<number>", normalized)
    normalized = " ".join(normalized.split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _parse(lines: list[str]) -> tuple[list[LogEventData], int]:
    timeline: list[LogEventData] = []
    rejected = 0
    for line_number, line in enumerate(lines, start=1):
        match = LOG_PATTERN.fullmatch(line)
        if match is None:
            rejected += 1
            continue
        timestamp = datetime.fromisoformat(match.group("timestamp").replace("Z", "+00:00"))
        message = _sanitize(match.group("message"))
        raw_level = match.group("level").lower()
        level = "warning" if raw_level == "warn" else raw_level
        timeline.append(
            {
                "line_number": line_number,
                "timestamp": timestamp.isoformat(),
                "level": level,
                "component": match.group("component") or "unknown",
                "message": message,
                "cluster_id": _cluster_id(message),
            }
        )
    timeline.sort(
        key=lambda item: (
            datetime.fromisoformat(str(item["timestamp"])),
            int(item["line_number"]),
        )
    )
    return timeline, rejected


def _cluster(timeline: list[LogEventData]) -> list[LogClusterData]:
    grouped: dict[str, list[LogEventData]] = defaultdict(list)
    for event in timeline:
        grouped[str(event["cluster_id"])].append(event)
    result: list[LogClusterData] = []
    for cluster_id, events in grouped.items():
        result.append(
            {
                "cluster_id": cluster_id,
                "count": len(events),
                "first_timestamp": events[0]["timestamp"],
                "last_timestamp": events[-1]["timestamp"],
                "levels": sorted({str(item["level"]) for item in events}),
                "representative": events[0]["message"],
                "line_numbers": [int(item["line_number"]) for item in events],
            }
        )
    return sorted(result, key=lambda item: (-int(item["count"]), str(item["cluster_id"])))


def _anomalies(
    timeline: list[LogEventData], clusters: list[LogClusterData]
) -> list[LogAnomalyData]:
    anomalies: list[LogAnomalyData] = []
    by_cluster = {str(item["cluster_id"]): item for item in clusters}
    for cluster in clusters:
        levels = set(cluster["levels"])
        if levels & {"error", "critical"}:
            anomalies.append(
                {
                    "anomaly_type": "severe_event",
                    "severity": "critical" if "critical" in levels else "high",
                    "cluster_id": cluster["cluster_id"],
                    "explanation": "The cluster contains an explicitly severe log level.",
                    "line_numbers": cluster["line_numbers"],
                }
            )
    grouped_events: dict[str, list[LogEventData]] = defaultdict(list)
    for event in timeline:
        grouped_events[str(event["cluster_id"])].append(event)
    for cluster_id, events in grouped_events.items():
        for start in range(len(events) - 2):
            first = datetime.fromisoformat(str(events[start]["timestamp"]))
            third = datetime.fromisoformat(str(events[start + 2]["timestamp"]))
            if third - first <= timedelta(seconds=10):
                cluster = by_cluster[cluster_id]
                anomalies.append(
                    {
                        "anomaly_type": "burst",
                        "severity": "medium",
                        "cluster_id": cluster_id,
                        "explanation": (
                            "At least three matching events occurred within ten seconds."
                        ),
                        "line_numbers": cluster["line_numbers"],
                    }
                )
                break
    return sorted(
        anomalies,
        key=lambda item: (
            {"critical": 0, "high": 1, "medium": 2}[str(item["severity"])],
            int(item["line_numbers"][0]),
        ),
    )


def _input_hash(request: AiAnalysisRequest, command: AiLogAnalysisCreate) -> str:
    value = {"request_id": request.request_id, **command.model_dump(mode="json")}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def log_analysis_response(
    analysis: AiLogAnalysis, *, request: AiAnalysisRequest, duplicate: bool = False
) -> AiLogAnalysisResponse:
    return AiLogAnalysisResponse(
        id=analysis.id,
        analysis_id=analysis.analysis_id,
        request_id=request.request_id,
        source=analysis.source,
        line_count=analysis.line_count,
        parsed_count=analysis.parsed_count,
        rejected_count=analysis.rejected_count,
        timeline=analysis.timeline,
        clusters=analysis.clusters,
        anomalies=analysis.anomalies,
        explanation=analysis.explanation,
        duplicate=duplicate,
        created_by_user_id=analysis.created_by_user_id,
        created_at=analysis.created_at,
    )


async def create_log_analysis(
    session: AsyncSession,
    *,
    request: AiAnalysisRequest,
    command: AiLogAnalysisCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiLogAnalysis, bool]:
    input_hash = _input_hash(request, command)
    existing = await session.scalar(
        select(AiLogAnalysis).where(AiLogAnalysis.analysis_id == command.analysis_id)
    )
    if existing is not None:
        if existing.input_hash == input_hash:
            return existing, True
        raise AiLogAnalysisConflictError()
    if request.task not in ALLOWED_TASKS:
        raise AiLogAnalysisContractError("the request task does not support log intelligence")
    existing_for_request = await session.scalar(
        select(AiLogAnalysis).where(AiLogAnalysis.request_id == request.id)
    )
    if existing_for_request is not None:
        raise AiLogAnalysisContractError("the request already has a log analysis")
    timeline, rejected = _parse(command.lines)
    if not timeline:
        raise AiLogAnalysisContractError("the batch contains no parseable log lines")
    first = datetime.fromisoformat(str(timeline[0]["timestamp"]))
    last = datetime.fromisoformat(str(timeline[-1]["timestamp"]))
    if last - first > timedelta(days=7):
        raise AiLogAnalysisContractError("the log timeline exceeds seven days")
    clusters = _cluster(timeline)
    anomalies = _anomalies(timeline, clusters)
    supporting = sorted({line for anomaly in anomalies for line in anomaly["line_numbers"]})[:50]
    explanation = {
        "summary": (
            f"Parsed {len(timeline)} of {len(command.lines)} lines into {len(clusters)} "
            f"cluster(s) and identified {len(anomalies)} deterministic anomaly signal(s)."
        ),
        "supporting_line_numbers": supporting,
        "evidence_refs": request.evidence_refs[:10],
        "limitations": [
            "The explanation uses deterministic log structure and severity only.",
            "A causal conclusion requires review of the cited evidence and vehicle state.",
        ],
    }
    analysis = AiLogAnalysis(
        analysis_id=command.analysis_id,
        input_hash=input_hash,
        request_id=request.id,
        created_by_user_id=actor_user_id,
        source=command.source,
        line_count=len(command.lines),
        parsed_count=len(timeline),
        rejected_count=rejected,
        timeline=timeline,
        clusters=clusters,
        anomalies=anomalies,
        explanation=explanation,
    )
    try:
        async with session.begin_nested():
            session.add(analysis)
            await session.flush()
    except IntegrityError as exc:
        raise AiLogAnalysisConflictError() from exc
    evidence = {
        "analysis_id": analysis.analysis_id,
        "request_id": request.request_id,
        "source": analysis.source,
        "line_count": analysis.line_count,
        "parsed_count": analysis.parsed_count,
        "rejected_count": analysis.rejected_count,
        "cluster_count": len(clusters),
        "anomaly_count": len(anomalies),
    }
    enqueue_event(
        session,
        event_type="atep.ai.log_analysis.completed.v1",
        aggregate_type="ai_log_analysis",
        aggregate_id=analysis.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ai_log_analysis.completed",
        resource_type="ai_log_analysis",
        resource_id=analysis.id,
        details=evidence,
        correlation_id=correlation_id,
    )
    return analysis, False


async def list_log_analyses(
    session: AsyncSession, *, limit: int, offset: int, source: str | None
) -> tuple[list[tuple[AiLogAnalysis, AiAnalysisRequest]], int]:
    filters = [] if source is None else [AiLogAnalysis.source == source]
    total = await session.scalar(select(func.count(AiLogAnalysis.id)).where(*filters))
    rows = await session.execute(
        select(AiLogAnalysis, AiAnalysisRequest)
        .join(AiAnalysisRequest, AiAnalysisRequest.id == AiLogAnalysis.request_id)
        .where(*filters)
        .order_by(AiLogAnalysis.created_at.desc(), AiLogAnalysis.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.tuples()), int(total or 0)


async def require_log_analysis(
    session: AsyncSession, analysis_id: str
) -> tuple[AiLogAnalysis, AiAnalysisRequest]:
    row = (
        await session.execute(
            select(AiLogAnalysis, AiAnalysisRequest)
            .join(AiAnalysisRequest, AiAnalysisRequest.id == AiLogAnalysis.request_id)
            .where(AiLogAnalysis.analysis_id == analysis_id)
        )
    ).one_or_none()
    if row is None:
        from atep.core.errors import ResourceNotFoundError

        raise ResourceNotFoundError("ai_log_analysis")
    return row[0], row[1]
