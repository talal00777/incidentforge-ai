"""Bounded, deterministic parsing of log records with source-line provenance."""

import hashlib
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import BinaryIO

VERSION = "m2.2"
MAX_LINE_BYTES = 64 * 1024
MAX_RECORD_BYTES = 64 * 1024
MAX_MULTILINE_LINES = 128
MAX_JSON_DEPTH = 64
MAX_MESSAGE = 4096
TIME_PREFIX = re.compile(
    r"^(?P<date>\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?)\s+(?P<body>.*)$",
    re.DOTALL,
)
SEVERITIES = re.compile(r"\b(DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|FATAL|CRITICAL)\b", re.I)
TRACE_CONTINUATION = re.compile(
    r"^(?:Traceback \(most recent call last\):|During handling of the above exception"
    r"|The above exception was the direct cause|Caused by:|Suppressed:"
    r"|at\s+|\.{3}\s+\d+\s+more|[\w.]+(?:Error|Exception):)",
    re.I,
)
SECRETS = [
    re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)\b(password|api[_-]?key|secret|token)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
]


def redact(message: str) -> str:
    text = message[:MAX_MESSAGE]
    text = SECRETS[0].sub(r"\1[REDACTED]", text)
    text = SECRETS[1].sub(r"\1=[REDACTED]", text)
    return SECRETS[2].sub("[REDACTED_EMAIL]", text)


def parse_timestamp(value: object) -> tuple[datetime | None, str]:
    if value is None or value == "":
        return None, "missing"
    if not isinstance(value, str):
        return None, "invalid"
    try:
        normalized = value.strip().replace(",", ".")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None, "invalid"
    if parsed.tzinfo is None:
        return None, "unknown_timezone"
    return parsed.astimezone(UTC), "explicit"


def _json_depth_ok(text: str) -> bool:
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "{[":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                return False
        elif char in "}]":
            depth -= 1
    return True


def _parse_mapping(data: object, start: int, end: int) -> tuple[dict | None, str | None]:
    if not isinstance(data, dict):
        return None, "invalid_record"
    message = data.get("message", data.get("body", ""))
    if not isinstance(message, str):
        return None, "invalid_message"
    occurred, quality = parse_timestamp(data.get("timestamp", data.get("time")))
    severity = str(data.get("level", data.get("severity", ""))).upper()[:16]
    service = str(data.get("service", ""))[:120]
    trace = str(data.get("trace_id", ""))[:128]
    return _event(start, end, occurred, quality, severity, service, trace, message), None


def _event(
    start: int,
    end: int,
    occurred: datetime | None,
    quality: str,
    severity: str,
    service: str,
    trace: str,
    message: str,
) -> dict:
    safe = redact(message)
    return {
        "line_start": start,
        "line_end": end,
        "occurred_at": occurred,
        "timestamp_quality": quality,
        "severity": severity,
        "service": service,
        "trace_id": trace,
        "redacted_message": safe,
        "fingerprint": hashlib.sha256((severity + ":" + safe).encode()).hexdigest(),
        "parser_version": VERSION,
    }


def parse_line(
    line: bytes, number: int, *, line_end: int | None = None
) -> tuple[dict | None, str | None]:
    """Parse one complete record; a multiline record may span several source lines."""
    if len(line) > MAX_RECORD_BYTES:
        return None, "record_too_long"
    try:
        text = line.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        return None, "invalid_utf8"
    if not text:
        return None, "empty_line"
    end = number if line_end is None else line_end
    if text.startswith(("{", "[")):
        if not _json_depth_ok(text):
            return None, "json_too_deep"
        try:
            return _parse_mapping(json.loads(text), number, end)
        except (ValueError, TypeError, RecursionError):
            return None, "invalid_json"
    match = TIME_PREFIX.match(text)
    occurred, quality = parse_timestamp(match.group("date")) if match else (None, "missing")
    message = match.group("body") if match else text
    found = SEVERITIES.search(message)
    severity = found.group(1).upper() if found else ""
    return _event(number, end, occurred, quality, severity, "", "", message), None


def _bounded_lines(handle: BinaryIO) -> Iterator[tuple[bytes | None, int, str | None]]:
    """Read physical lines without loading an arbitrarily long line into memory."""
    number = 0
    while part := handle.readline(MAX_LINE_BYTES + 1):
        number += 1
        if len(part) > MAX_LINE_BYTES:
            while part and not part.endswith(b"\n"):
                part = handle.readline(MAX_LINE_BYTES + 1)
            yield None, number, "line_too_long"
        else:
            yield part, number, None


def _continuation(text: str) -> bool:
    return bool(text.startswith((" ", "\t")) or TRACE_CONTINUATION.match(text))


def _plain_records(handle: BinaryIO) -> Iterator[tuple[dict | None, str | None]]:
    pending: list[str] = []
    start = 0
    end = 0
    size = 0
    discarding = False

    for raw, number, warning in _bounded_lines(handle):
        if warning:
            if pending:
                yield parse_line("\n".join(pending).encode("utf-8"), start, line_end=end)
                pending.clear()
            discarding = False
            size = 0
            yield None, warning
            continue
        assert raw is not None
        try:
            text = raw.decode("utf-8-sig").rstrip("\r\n")
        except UnicodeDecodeError:
            if pending:
                yield parse_line("\n".join(pending).encode("utf-8"), start, line_end=end)
                pending.clear()
            discarding = False
            size = 0
            yield None, "invalid_utf8"
            continue
        continuation = _continuation(text) and not text.lstrip().startswith(("{", "["))
        if discarding and continuation:
            continue
        if discarding:
            discarding = False
        if pending and continuation and not pending[0].lstrip().startswith(("{", "[")):
            next_size = size + 1 + len(raw)
            if next_size > MAX_RECORD_BYTES or len(pending) >= MAX_MULTILINE_LINES:
                pending.clear()
                size = 0
                discarding = True
                yield None, "record_too_long"
                continue
            pending.append(text)
            size = next_size
            end = number
            continue
        if pending:
            yield parse_line("\n".join(pending).encode("utf-8"), start, line_end=end)
        pending = [text]
        start = end = number
        size = len(raw)
    if pending:
        yield parse_line("\n".join(pending).encode("utf-8"), start, line_end=end)


def _parse_array_member(raw: bytes, start: int, end: int) -> tuple[dict | None, str | None]:
    try:
        text = raw.decode("utf-8-sig")
        if not _json_depth_ok(text):
            return None, "json_too_deep"
        data = json.loads(text)
    except UnicodeDecodeError:
        return None, "invalid_utf8"
    except (ValueError, TypeError, RecursionError):
        return None, "invalid_json"
    return _parse_mapping(data, start, end)


def _array_records(handle: BinaryIO) -> Iterator[tuple[dict | None, str | None]]:
    """Stream a top-level JSON array without buffering the full document.

    Each element is limited to MAX_RECORD_BYTES and must be a JSON object.
    The array's structural syntax is also validated.
    """
    started = False
    ended = False
    expecting = True
    saw_item = False
    in_item = False
    in_string = False
    escaped = False
    depth = 0
    overflow = False
    buffer = bytearray()
    line = 1
    start_line = 1
    end_line = 1
    for chunk in iter(lambda: handle.read(16 * 1024), b""):
        for char in chunk:
            current_line = line
            if char == 10:
                line += 1
            if not started:
                if char in b" \t\r\n":
                    continue
                if char != ord("["):
                    yield None, "invalid_json"
                    return
                started = True
                continue
            if ended:
                if char not in b" \t\r\n":
                    yield None, "invalid_json"
                    return
                continue
            if not in_item:
                if char in b" \t\r\n":
                    continue
                if char == ord("]"):
                    if expecting and saw_item:
                        yield None, "invalid_json"
                    ended = True
                    continue
                if not expecting or char == ord(","):
                    yield None, "invalid_json"
                    return
                in_item = True
                expecting = False
                saw_item = True
                start_line = current_line
                depth = 0
                overflow = False
                buffer.clear()
            if not in_string and depth == 0 and char in (ord(","), ord("]")):
                if overflow:
                    yield None, "record_too_long"
                else:
                    yield _parse_array_member(bytes(buffer), start_line, end_line)
                in_item = False
                expecting = char == ord(",")
                if char == ord("]"):
                    ended = True
                continue
            if not overflow:
                if len(buffer) < MAX_RECORD_BYTES:
                    buffer.append(char)
                else:
                    overflow = True
                    buffer.clear()
            if char not in b" \t\r\n":
                end_line = current_line
            if in_string:
                if escaped:
                    escaped = False
                elif char == ord("\\"):
                    escaped = True
                elif char == ord('"'):
                    in_string = False
            elif char == ord('"'):
                in_string = True
            elif char in (ord("{"), ord("[")):
                depth += 1
            elif char in (ord("}"), ord("]")):
                depth -= 1
    if not started or not ended:
        yield None, "invalid_json"


def _single_json_document(handle: BinaryIO) -> Iterator[tuple[dict | None, str | None]]:
    raw = handle.read(MAX_RECORD_BYTES + 1)
    if len(raw) > MAX_RECORD_BYTES:
        yield None, "record_too_long"
        return
    end = len(raw.rstrip(b" \t\r\n").split(b"\n"))
    yield parse_line(raw, 1, line_end=end)


def iter_records(handle: BinaryIO) -> Iterator[tuple[dict | None, str | None]]:
    """Yield accepted events or bounded rejection diagnostics from a seekable binary stream."""
    prefix = handle.read(4096).lstrip(b"\xef\xbb\xbf \t\r\n")
    handle.seek(0)
    if prefix.startswith(b"["):
        if handle.read(3) != b"\xef\xbb\xbf":
            handle.seek(0)
        yield from _array_records(handle)
    elif prefix.startswith(b"{") and prefix.split(b"\n", 1)[0].strip() == b"{":
        yield from _single_json_document(handle)
    else:
        yield from _plain_records(handle)
