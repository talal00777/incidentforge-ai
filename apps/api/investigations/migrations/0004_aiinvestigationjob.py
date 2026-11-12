import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("investigations", "0003_postmortem_versions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AIInvestigationJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(blank=True, max_length=64)),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("provider", models.CharField(max_length=32)),
                ("model_id", models.CharField(max_length=160)),
                ("prompt_profile", models.CharField(max_length=32)),
                ("temperature", models.FloatField()),
                ("max_output_tokens", models.PositiveSmallIntegerField()),
                ("state", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("retry_wait", "Retry wait"), ("cancelling", "Cancelling"), ("cancelled", "Cancelled"), ("succeeded", "Succeeded"), ("failed", "Failed")], default="queued", max_length=16)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("claim_token", models.UUIDField(blank=True, null=True)),
                ("lease_until", models.DateTimeField(blank=True, null=True)),
                ("available_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("cancel_requested", models.BooleanField(default=False)),
                ("error_code", models.CharField(blank=True, max_length=40)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("attempt", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to="investigations.investigationattempt")),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ai_jobs", to="incidents.incident")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="evidence.evidencesnapshot")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["owner", "-requested_at"], name="inv_ai_owner_date_idx"),
                    models.Index(fields=["state", "available_at"], name="inv_ai_state_ready_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AIJobExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveSmallIntegerField()),
                ("state", models.CharField(default="running", max_length=16)),
                ("error_code", models.CharField(blank=True, max_length=40)),
                ("started_at", models.DateTimeField()),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="executions", to="investigations.aiinvestigationjob")),
            ],
        ),
        migrations.AddConstraint(
            model_name="aiinvestigationjob",
            constraint=models.UniqueConstraint(
                condition=models.Q(state__in=["queued", "running", "retry_wait", "cancelling"]),
                fields=("incident",),
                name="inv_ai_active_incident_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="aiinvestigationjob",
            constraint=models.UniqueConstraint(
                condition=~models.Q(idempotency_key=""),
                fields=("owner", "idempotency_key"),
                name="inv_ai_owner_key_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="aijobexecution",
            constraint=models.UniqueConstraint(fields=("job", "number"), name="inv_ai_execution_number_uniq"),
        ),
    ]
