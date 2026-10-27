import hashlib
import os
from pathlib import Path
from uuid import uuid4

from django.conf import settings


def root():
    location = Path(settings.INGESTION_STORAGE_ROOT).resolve()
    location.mkdir(parents=True, exist_ok=True, mode=0o700)
    return location


def store(upload):
    object_key = uuid4().hex
    destination = root() / object_key
    digest = hashlib.sha256()
    written = 0
    try:
        with destination.open("xb") as handle:
            os.chmod(destination, 0o600)
            for chunk in upload.chunks():
                written += len(chunk)
                if written > settings.INGESTION_MAX_FILE_BYTES:
                    raise ValueError("file_too_large")
                digest.update(chunk)
                handle.write(chunk)
        return object_key, digest.hexdigest(), written
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def path_for(object_key):
    if len(object_key) != 32 or any(char not in "0123456789abcdef" for char in object_key):
        raise ValueError("invalid_object_key")
    return root() / object_key
