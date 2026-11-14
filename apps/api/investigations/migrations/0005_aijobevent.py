import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("investigations", "0004_aiinvestigationjob"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AIJobEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[
                    ("submitted", "Submitted"), ("claimed", "Claimed"),
                    ("cancel_requested", "Cancel requested"), ("cancelled", "Cancelled"),
                    ("retry_scheduled", "Retry scheduled"), ("interrupted", "Interrupted"),
                    ("completed", "Completed"), ("failed", "Failed"),
                ], max_length=20)),
                ("attempt_number", models.PositiveSmallIntegerField(default=0)),
                ("error_code", models.CharField(blank=True, max_length=40)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="investigations.aiinvestigationjob")),
            ],
            options={
                "ordering": ("occurred_at", "id"),
                "indexes": [models.Index(fields=["job", "-occurred_at"], name="inv_ai_event_job_date_idx")],
            },
        ),
    ]
