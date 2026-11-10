from uuid import UUID

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from incidents.models import Incident
from incidents.retention import ACTIVE_JOBS, purge_report_content, retention_cutoff


class Command(BaseCommand):
    help = "List or remove investigation content from deleted incidents."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument(
            "--minimum-deleted-days", type=int, default=settings.RETENTION_REPORT_DAYS
        )
        parser.add_argument("--max-incidents", type=int, default=25)
        parser.add_argument("--after-incident-id")

    def handle(self, *args, **options):
        days = options["minimum_deleted_days"]
        limit = options["max_incidents"]
        if not 1 <= days <= 3650:
            raise CommandError("minimum-deleted-days must be between 1 and 3650")
        if not 1 <= limit <= 250:
            raise CommandError("max-incidents must be between 1 and 250")

        after = options["after_incident_id"]
        if after is not None:
            try:
                after = UUID(after)
            except ValueError as exc:
                raise CommandError("Invalid after-incident-id UUID") from exc

        cutoff = retention_cutoff(days)
        candidates = Incident.objects.filter(
            deleted_at__isnull=False,
            deleted_at__lte=cutoff,
            report_purge_receipt__isnull=True,
        ).exclude(ingestion_jobs__state__in=ACTIVE_JOBS)
        if after is not None:
            candidates = candidates.filter(id__gt=after)
        candidate_ids = list(candidates.order_by("id").values_list("id", flat=True)[:limit])

        counts = {
            "postmortems": 0,
            "review_revisions": 0,
            "reviews": 0,
            "reports": 0,
            "attempts": 0,
            "snapshots": 0,
        }
        eligible = purged = skipped_active = 0
        for incident_id in candidate_ids:
            state, removed = purge_report_content(
                incident_id,
                cutoff=cutoff,
                retention_days=days,
                execute=options["execute"],
            )
            if state == "active":
                skipped_active += 1
            if state != "eligible":
                continue
            eligible += 1
            purged += int(options["execute"])
            for name, value in removed.items():
                counts[name] += value

        summary = " ".join(f"{name}={count}" for name, count in counts.items())
        self.stdout.write(
            f"eligible={eligible} purged={purged} skipped_active={skipped_active} "
            f"{summary} executed={options['execute']} "
            f"last_incident_id={candidate_ids[-1] if candidate_ids else 'none'}"
        )
