"""Validation and conservative redaction for untrusted incident evidence."""

import codecs
import re

from django.conf import settings

SUPPORTED_EXTENSIONS = (".log", ".txt", ".json", ".jsonl")
REJECTED_SIGNATURES = (
    b"PK\x03\x04",  # ZIP-based containers
    b"PK\x05\x06",
    b"\x1f\x8b",  # gzip
    b"BZh",
    b"\xfd7zXZ\x00",
    b"7z\xbc\xaf\x27\x1c",
    b"%PDF-",
    b"\x7fELF",
    b"MZ",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"SQLite format 3\x00",
)
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
AUTHORIZATION = re.compile(r"(?i)\b(authorization\s*:\s*(?:bearer|basic)\s+)[^\s,;]+")
COOKIES = re.compile(r"(?i)\b((?:set-cookie|cookie)\s*:\s*)[^\r\n]+")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|passphrase|api[_-]?key|secret|client[_-]?secret|"
    r"access[_-]?token|refresh[_-]?token|token|aws_secret_access_key|"
    r"private[_-]?key)\b(?P<separator>[\"']?\s*[:=]\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;\"'}]+)"
)
URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
GITHUB_TOKEN = re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")
MAX_MESSAGE = 4096


class UploadRejected(ValueError):
    """Public, content-independent validation failure."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(detail)


def _hide_secret_value(match: re.Match[str]) -> str:
    prefix = match.group(0)[: match.start("value") - match.start(0)]
    secret = match.group("value")
    if secret.startswith(('"', "'")) and secret.endswith(secret[0]):
        return prefix + secret[0] + "[REDACTED]" + secret[0]
    return prefix + "[REDACTED]"


def redact_message(value: str) -> str:
    """Mask recognized secrets before database persistence or external processing.

    This is a defense-in-depth filter, not a guarantee of complete PII discovery.
    """
    text = value[:MAX_MESSAGE]
    text = URL_USERINFO.sub(r"\1[REDACTED]@", text)
    text = AUTHORIZATION.sub(r"\1[REDACTED]", text)
    text = COOKIES.sub(r"\1[REDACTED]", text)
    text = SECRET_ASSIGNMENT.sub(_hide_secret_value, text)
    text = AWS_ACCESS_KEY.sub("[REDACTED]", text)
    text = GITHUB_TOKEN.sub("[REDACTED]", text)
    return EMAIL.sub("[REDACTED_EMAIL]", text)


def safe_filename(original: str) -> str:
    # Browser-supplied filenames are display labels, never filesystem paths.
    basename = re.split(r"[/\\]", original)[-1].strip()
    basename = CONTROL_CHARACTERS.sub("_", basename)
    if not basename or basename in (".", ".."):
        raise UploadRejected("invalid_filename", "A valid filename is required.")
    if not basename.lower().endswith(SUPPORTED_EXTENSIONS):
        raise UploadRejected(
            "unsupported_file_type", "Allowed file types: .log, .txt, .json, .jsonl."
        )
    return redact_message(basename)[:255]


def validate_upload(upload) -> str:
    """Stream-check size, type signatures, controls and complete UTF-8 content.

    Resets the upload to offset zero even on failure; storage will re-check size.
    """
    filename = safe_filename(upload.name)
    if upload.size == 0 or upload.size > settings.INGESTION_MAX_FILE_BYTES:
        raise UploadRejected("invalid_file_size", "File is empty or exceeds the size limit.")

    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    total = 0
    prefix = b""
    first_visible = None
    try:
        upload.seek(0)
        for chunk in upload.chunks():
            total += len(chunk)
            if total > settings.INGESTION_MAX_FILE_BYTES:
                raise UploadRejected("invalid_file_size", "File exceeds the size limit.")
            if len(prefix) < 32:
                prefix += chunk[: 32 - len(prefix)]
                if any(prefix.startswith(signature) for signature in REJECTED_SIGNATURES):
                    raise UploadRejected("binary_file", "Only UTF-8 text evidence is accepted.")
            try:
                decoded = decoder.decode(chunk)
            except UnicodeDecodeError as exc:
                raise UploadRejected("invalid_utf8", "Evidence must be valid UTF-8 text.") from exc
            if CONTROL_CHARACTERS.search(decoded):
                raise UploadRejected("binary_file", "Binary/control characters are not accepted.")
            if first_visible is None:
                first_visible = next((ch for ch in decoded if not ch.isspace()), None)
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError as exc:
            raise UploadRejected("invalid_utf8", "Evidence must be valid UTF-8 text.") from exc
        if total == 0 or first_visible is None:
            raise UploadRejected("empty_content", "Evidence must contain text records.")
        lowered = filename.lower()
        if lowered.endswith(".json") and first_visible not in ("{", "["):
            raise UploadRejected(
                "invalid_json_type", "JSON evidence must start with an object or array."
            )
        if lowered.endswith(".jsonl") and first_visible != "{":
            raise UploadRejected("invalid_jsonl_type", "JSONL evidence must begin with an object.")
        return filename
    finally:
        upload.seek(0)
