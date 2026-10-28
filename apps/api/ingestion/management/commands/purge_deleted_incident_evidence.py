"""Purge evidence for aged soft-deleted incidents without removing audit history."""

import re
import stat
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from incidents.models import Incident
from ingestion.models import IngestionJob, LogEvent, LogSource

OBJECT_KEY = re.compile(r"[a-f0-9]{32}\Z")
ACTIVE = (IngestionJob.State.QUEUED, IngestionJob.State.RUNNING)


def stored_path(key: str) -> Path:
    if not OBJECT_KEY.fullmatch(key):
        raise CommandError("Stored evidence contains an invalid object key")
    return Path(settings.INGESTION_STORAGE_ROOT).resolve() / key


def file_identity(path: Path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise CommandError("Stored evidence is not a regular file")
    return metadata.st_dev, metadata.st_ino


class Command(BaseCommand):
    help = "Report or remove evidence of soft-deleted incidents, preserving audit history."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--minimum-deleted-days", type=int, default=30)
        parser.add_argument("--max-incidents", type=int, default=25)
        parser.add_argument("--after-incident-id", type=str)

    def handle(self, *args, **options):
        if not 1 <= options["minimum_deleted_days"] <= 3650:
            raise CommandError("minimum-deleted-days must be between 1 and 3650")
        if not 1 <= options["max_incidents"] <= 250:
            raise CommandError("max-incidents must be between 1 and 250")

        cutoff = timezone.now() - timedelta(days=options["minimum_deleted_days"])
        after = options["after_incident_id"]
        if after is not None:
            try:
                after = UUID(after)
            except ValueError as exc:
                raise CommandError("Invalid after-incident-id UUID") from exc
        candidates = Incident.objects.filter(
            deleted_at__isnull=False, deleted_at__lte=cutoff
        )
        if after is not None:
            candidates = candidates.filter(id__gt=after)
        candidate_ids = list(
            candidates.order_by("id").values_list("id", flat=True)[: options["max_incidents"]]
        )
        eligible = skipped_active = deleted_files = missing_files = failed_files = 0
        deleted_sources = deleted_events = 0

        for pk in candidate_ids:
            files = []
            with transaction.atomic():
                incident = Incident.objects.select_for_update().filter(pk=pk).first()
                if incident is None or not incident.deleted_at or incident.deleted_at > cutoff:
                    continue
                jobs = IngestionJob.objects.select_for_update().filter(incident=incident)
                if jobs.filter(state__in=ACTIVE).exists():
                    skipped_active += 1
                    continue

                sources = list(LogSource.objects.select_for_update().filter(incident=incident))
                for source in sources:
                    path = stored_path(source.object_key)
                    files.append((path, file_identity(path)))

                eligible += 1
                if not options["execute"]:
                    continue

                deleted_events += LogEvent.objects.filter(incident=incident).count()
                deleted_sources += len(sources)
                LogEvent.objects.filter(incident=incident).delete()
                LogSource.objects.filter(incident=incident).delete()
                jobs.delete()

            if not options["execute"]:
                continue
            for path, identity in files:
                if identity is None:
                    missing_files += 1
                    continue
                try:
                    if file_identity(path) != identity:
                        failed_files += 1
                        continue
                    if LogSource.objects.filter(object_key=path.name).exists():
                        failed_files += 1
                        continue
                    path.unlink()
                    deleted_files += 1
                except OSError:
                    failed_files += 1
                except CommandError:
                    failed_files += 1

        self.stdout.write(
            f"eligible_incidents={eligible} skipped_active={skipped_active} "
            f"deleted_events={deleted_events} deleted_sources={deleted_sources} "
            f"deleted_files={deleted_files} missing_files={missing_files} "
            f"failed_files={failed_files} executed={options['execute']} "
            f"last_incident_id={candidate_ids[-1] if candidate_ids else 'none'}"
        )
        if failed_files:
            raise CommandError("Evidence purge encountered filesystem failures")
