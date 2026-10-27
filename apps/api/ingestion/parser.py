import hashlib
import json
import re
from datetime import UTC, datetime

VERSION = "m2.1"
MAX_LINE_BYTES = 64 * 1024
MAX_MESSAGE = 4096
TIME_PREFIX = re.compile(
    r"^(?P<date>\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?)\s+(?P<body>.*)$"
)
SEVERITIES = re.compile(r"\b(DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|FATAL|CRITICAL)\b", re.I)
SECRETS = [
    re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)\b(password|api[_-]?key|secret|token)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
]


def redact(message):
    text = message[:MAX_MESSAGE]
    text = SECRETS[0].sub(r"\1[REDACTED]", text)
    text = SECRETS[1].sub(r"\1=[REDACTED]", text)
    text = SECRETS[2].sub("[REDACTED_EMAIL]", text)
    return text


def parse_timestamp(value):
    if not isinstance(value, str):
        return None, "missing"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace(",", "."))
    except ValueError:
        return None, "invalid"
    if parsed.tzinfo is None:
        return None, "unknown_timezone"
    return parsed.astimezone(UTC), "explicit"


def parse_line(line, number):
    if len(line) > MAX_LINE_BYTES:
        return None, "line_too_long"
    try:
        text = line.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "invalid_utf8"
    text = text.strip()
    if not text:
        return None, "empty_line"
    data = None
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None, "invalid_json"
        if not isinstance(data, dict):
            return None, "invalid_record"
    if data is not None:
        msg = data.get("message", data.get("body", ""))
        if not isinstance(msg, str):
            return None, "invalid_message"
        occurred, quality = parse_timestamp(data.get("timestamp", data.get("time")))
        severity = str(data.get("level", data.get("severity", ""))).upper()[:16]
        service = str(data.get("service", ""))[:120]
        trace = str(data.get("trace_id", ""))[:128]
    else:
        match = TIME_PREFIX.match(text)
        occurred, quality = parse_timestamp(match.group("date")) if match else (None, "missing")
        msg = match.group("body") if match else text
        found = SEVERITIES.search(msg)
        severity = found.group(1).upper() if found else ""
        service = ""
        trace = ""
    safe = redact(msg)
    return {
        "line_start": number,
        "line_end": number,
        "occurred_at": occurred,
        "timestamp_quality": quality,
        "severity": severity,
        "service": service,
        "trace_id": trace,
        "redacted_message": safe,
        "fingerprint": hashlib.sha256((severity + ":" + safe).encode()).hexdigest(),
        "parser_version": VERSION,
    }, None
