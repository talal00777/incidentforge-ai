import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("incidents", "0001_initial"),
        ("evidence", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InvestigationAttempt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("snapshot_sha256", models.CharField(max_length=64)),
                ("provider", models.CharField(max_length=32)),
                ("model_id", models.CharField(max_length=160)),
                ("prompt_profile", models.CharField(max_length=32)),
                ("status", models.CharField(default="started", max_length=12)),
                ("failure_code", models.CharField(blank=True, max_length=40)),
                ("consent_accepted_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="incidents.incident")),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="evidence.evidencesnapshot")),
            ],
        ),
        migrations.CreateModel(
            name="InvestigationReport",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("snapshot_sha256", models.CharField(max_length=64)),
                ("provider", models.CharField(max_length=32)),
                ("model_id", models.CharField(max_length=160)),
                ("temperature", models.FloatField()),
                ("max_output_tokens", models.PositiveSmallIntegerField()),
                ("prompt_profile", models.CharField(max_length=32)),
                ("prompt_version", models.CharField(max_length=16)),
                ("response_schema_version", models.CharField(max_length=16)),
                ("report", models.JSONField()),
                ("input_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("output_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("consent_accepted_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("attempt", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to="investigations.investigationattempt")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="investigation_reports", to="incidents.incident")),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="evidence.evidencesnapshot")),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddIndex(
            model_name="investigationreport",
            index=models.Index(fields=["incident", "-created_at"], name="inv_report_inc_date_idx"),
        ),
    ]
