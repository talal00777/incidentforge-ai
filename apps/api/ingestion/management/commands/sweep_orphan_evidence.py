"""Explicit reconciliation of aged, unreferenced raw evidence files."""

import re
import stat
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ingestion.models import LogSource
from ingestion.storage import root

OBJECT_KEY = re.compile(r"[a-f0-9]{32}\Z")


class Command(BaseCommand):
    help = "Inspect orphaned raw evidence; delete only with --execute."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--minimum-age-hours", type=int, default=24)
        parser.add_argument("--max-files", type=int, default=500)

    def handle(self, *args, **options):
        if options["minimum_age_hours"] < 1:
            raise CommandError("minimum-age-hours must be at least 1")
        if not 1 <= options["max_files"] <= 5000:
            raise CommandError("max-files must be between 1 and 5000")

        directory = root()
        cutoff = time.time() - options["minimum_age_hours"] * 3600
        examined = 0
        candidates = 0
        deleted = 0
        for path in directory.iterdir():
            if examined >= options["max_files"]:
                break
            examined += 1
            if not OBJECT_KEY.fullmatch(path.name):
                continue
            try:
                metadata = path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mtime > cutoff:
                continue
            if LogSource.objects.filter(object_key=path.name).exists():
                continue
            candidates += 1
            if options["execute"]:
                # Recheck identity and age immediately before deletion.
                try:
                    latest = path.lstat()
                    if (
                        not stat.S_ISREG(latest.st_mode)
                        or latest.st_ino != metadata.st_ino
                        or latest.st_dev != metadata.st_dev
                        or latest.st_mtime > cutoff
                        or LogSource.objects.filter(object_key=path.name).exists()
                    ):
                        continue
                    Path(path).unlink()
                    deleted += 1
                except FileNotFoundError:
                    continue
        mode = "EXECUTED" if options["execute"] else "DRY RUN"
        self.stdout.write(
            f"{mode}: examined={examined}, orphan_candidates={candidates}, deleted={deleted}"
        )
