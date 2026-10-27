import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL), ("incidents", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="IngestionJob",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("state", models.CharField(max_length=12, choices=[("queued", "Queued"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed")], default="queued")),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("accepted", models.PositiveIntegerField(default=0)),
                ("rejected", models.PositiveIntegerField(default=0)),
                ("error_code", models.CharField(max_length=64, blank=True)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(null=True, blank=True)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                ("incident", models.ForeignKey(to="incidents.incident", on_delete=django.db.models.deletion.PROTECT, related_name="ingestion_jobs")),
                ("owner", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.CreateModel(
            name="LogSource",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("filename", models.CharField(max_length=255)),
                ("object_key", models.CharField(max_length=150, unique=True)),
                ("sha256", models.CharField(max_length=64)),
                ("byte_size", models.PositiveIntegerField()),
                ("parser_version", models.CharField(max_length=32, default="m2.1")),
                ("state", models.CharField(max_length=12, choices=[("queued", "Queued"), ("complete", "Complete"), ("failed", "Failed")], default="queued")),
                ("accepted", models.PositiveIntegerField(default=0)),
                ("rejected", models.PositiveIntegerField(default=0)),
                ("warnings", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("incident", models.ForeignKey(to="incidents.incident", on_delete=django.db.models.deletion.PROTECT, related_name="log_sources")),
                ("job", models.ForeignKey(to="ingestion.ingestionjob", on_delete=django.db.models.deletion.PROTECT, related_name="sources")),
            ],
        ),
        migrations.CreateModel(
            name="LogEvent",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("line_start", models.PositiveIntegerField()),
                ("line_end", models.PositiveIntegerField()),
                ("occurred_at", models.DateTimeField(null=True, blank=True)),
                ("observed_at", models.DateTimeField()),
                ("timestamp_quality", models.CharField(max_length=32)),
                ("severity", models.CharField(max_length=16, blank=True)),
                ("service", models.CharField(max_length=120, blank=True)),
                ("trace_id", models.CharField(max_length=128, blank=True)),
                ("redacted_message", models.TextField(max_length=4096)),
                ("fingerprint", models.CharField(max_length=64)),
                ("parser_version", models.CharField(max_length=32, default="m2.1")),
                ("incident", models.ForeignKey(to="incidents.incident", on_delete=django.db.models.deletion.PROTECT, related_name="log_events")),
                ("source", models.ForeignKey(to="ingestion.logsource", on_delete=django.db.models.deletion.PROTECT, related_name="events")),
            ],
        ),
        migrations.AddIndex(model_name="ingestionjob", index=models.Index(fields=["incident", "-requested_at"], name="ing_job_inc_date_idx")),
        migrations.AddIndex(model_name="logsource", index=models.Index(fields=["incident", "created_at"], name="ing_src_inc_date_idx")),
        migrations.AddIndex(model_name="logevent", index=models.Index(fields=["incident", "occurred_at"], name="ing_evt_time_idx")),
        migrations.AddIndex(model_name="logevent", index=models.Index(fields=["incident", "severity", "occurred_at"], name="ing_evt_severity_idx")),
        migrations.AddConstraint(model_name="logevent", constraint=models.UniqueConstraint(fields=["source", "line_start", "line_end", "parser_version"], name="ing_event_idempotence")),
    ]
