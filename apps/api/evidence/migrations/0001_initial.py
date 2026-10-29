import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("incidents", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EvidenceSnapshot",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("entries", models.JSONField()),
                ("sha256", models.CharField(max_length=64)),
                ("item_count", models.PositiveSmallIntegerField()),
                ("characters", models.PositiveIntegerField()),
                ("payload_bytes", models.PositiveIntegerField()),
                ("selection_version", models.CharField(max_length=16)),
                ("privacy_policy_version", models.CharField(max_length=16)),
                ("consent_accepted_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
                ),
                (
                    "incident",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="evidence_snapshots", to="incidents.incident"),
                ),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddIndex(
            model_name="evidencesnapshot",
            index=models.Index(fields=["incident", "-created_at"], name="evid_snap_inc_date_idx"),
        ),
    ]
