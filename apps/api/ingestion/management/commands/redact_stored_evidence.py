"""Reapply the current redactor to stored normalized evidence."""

import hashlib
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ingestion.models import IngestionJob, LogEvent, LogSource
from ingestion.security import redact_message

ACTIVE = (IngestionJob.State.QUEUED, IngestionJob.State.RUNNING)


def sanitized_fields(event):
    message = redact_message(event.redacted_message)
    service = redact_message(event.service)[:120]
    trace_id = redact_message(event.trace_id)[:128]
    if (message, service, trace_id) == (
        event.redacted_message,
        event.service,
        event.trace_id,
    ):
        return {}
    return {
        "redacted_message": message,
        "service": service,
        "trace_id": trace_id,
        "fingerprint": hashlib.sha256((event.severity + ":" + message).encode()).hexdigest(),
    }


class Command(BaseCommand):
    help = "Audit or update stored normalized evidence using the current redaction rules."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--incident-id", type=str)
        parser.add_argument("--max-events", type=int, default=5000)
        parser.add_argument("--max-sources", type=int, default=500)
        parser.add_argument("--after-event-id", type=str)
        parser.add_argument("--after-source-id", type=str)

    def handle(self, *args, **options):
        if not 1 <= options["max_events"] <= 50_000:
            raise CommandError("max-events must be between 1 and 50000")
        if not 1 <= options["max_sources"] <= 5000:
            raise CommandError("max-sources must be between 1 and 5000")

        def optional_uuid(option):
            value = options[option]
            if value is None:
                return None
            try:
                return UUID(value)
            except ValueError as exc:
                raise CommandError(f"Invalid {option} UUID") from exc

        incident_id = optional_uuid("incident_id")
        after_event = optional_uuid("after_event_id")
        after_source = optional_uuid("after_source_id")

        events = LogEvent.objects.select_related("source__job").order_by("id")
        sources = LogSource.objects.select_related("job").order_by("id")
        if incident_id is not None:
            events = events.filter(incident_id=incident_id)
            sources = sources.filter(incident_id=incident_id)
        if after_event is not None:
            events = events.filter(id__gt=after_event)
        if after_source is not None:
            sources = sources.filter(id__gt=after_source)

        event_ids = list(events.values_list("id", flat=True)[: options["max_events"]])
        source_ids = list(sources.values_list("id", flat=True)[: options["max_sources"]])
        scanned_events = changed_events = changed_sources = skipped_active = 0

        for pk in event_ids:
            with transaction.atomic():
                event = (
                    LogEvent.objects.select_for_update()
                    .select_related("source__job")
                    .filter(pk=pk)
                    .first()
                )
                if event is None:
                    continue
                scanned_events += 1
                if event.source.job.state in ACTIVE:
                    skipped_active += 1
                    continue
                updates = sanitized_fields(event)
                if not updates:
                    continue
                changed_events += 1
                if options["execute"]:
                    LogEvent.objects.filter(pk=pk).update(**updates)

        scanned_sources = 0
        for pk in source_ids:
            with transaction.atomic():
                source = (
                    LogSource.objects.select_for_update()
                    .select_related("job")
                    .filter(pk=pk)
                    .first()
                )
                if source is None:
                    continue
                scanned_sources += 1
                if source.job.state in ACTIVE:
                    skipped_active += 1
                    continue
                filename = redact_message(source.filename)[:255]
                if filename == source.filename:
                    continue
                changed_sources += 1
                if options["execute"]:
                    LogSource.objects.filter(pk=pk).update(filename=filename)

        self.stdout.write(
            f"scanned_events={scanned_events} changed_events={changed_events} "
            f"scanned_sources={scanned_sources} changed_sources={changed_sources} "
            f"skipped_active={skipped_active} executed={options['execute']} "
            f"last_event_id={event_ids[-1] if event_ids else 'none'} "
            f"last_source_id={source_ids[-1] if source_ids else 'none'}"
        )
