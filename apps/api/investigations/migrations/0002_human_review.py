import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("investigations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InvestigationReview",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("latest_revision", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "report",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="human_review",
                        to="investigations.investigationreport",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="InvestigationReviewRevision",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("number", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("reviewed", "Reviewed")],
                        max_length=16,
                    ),
                ),
                ("impact_notes", models.TextField(blank=True)),
                ("remediation_notes", models.TextField(blank=True)),
                ("hypotheses", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "review",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revisions",
                        to="investigations.investigationreview",
                    ),
                ),
            ],
            options={"ordering": ("-number",)},
        ),
        migrations.AddConstraint(
            model_name="investigationreviewrevision",
            constraint=models.UniqueConstraint(
                fields=("review", "number"), name="inv_review_revision_unique"
            ),
        ),
    ]
