"""Report aggregate investigation execution state without exposing incident data."""

import json

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from investigations.models import AIInvestigationJob


class Command(BaseCommand):
    help = "Summarize investigation job states and overdue leases."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        now = timezone.now()
        counts = {state: 0 for state in AIInvestigationJob.State.values}
        for row in AIInvestigationJob.objects.values("state").annotate(count=Count("id")):
            counts[row["state"]] = row["count"]
        running = AIInvestigationJob.objects.filter(state__in=["running", "cancelling"])
        pending = AIInvestigationJob.objects.filter(state__in=["queued", "retry_wait"])
        summary = {
            "states": counts,
            "missing_leases": running.filter(lease_until__isnull=True).count(),
            "expired_leases": running.filter(lease_until__lte=now).count(),
            "due_pending": pending.filter(available_at__lte=now).count(),
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(summary, sort_keys=True))
        else:
            for state, count in counts.items():
                self.stdout.write(f"{state}: {count}")
            for key in ("missing_leases", "expired_leases", "due_pending"):
                self.stdout.write(f"{key}: {summary[key]}")
