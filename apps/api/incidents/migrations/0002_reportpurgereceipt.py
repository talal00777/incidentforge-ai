import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("incidents", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ReportPurgeReceipt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("completed_at", models.DateTimeField(auto_now_add=True)),
                ("retention_days", models.PositiveSmallIntegerField()),
                ("postmortems", models.PositiveIntegerField(default=0)),
                ("review_revisions", models.PositiveIntegerField(default=0)),
                ("reviews", models.PositiveIntegerField(default=0)),
                ("reports", models.PositiveIntegerField(default=0)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("snapshots", models.PositiveIntegerField(default=0)),
                (
                    "incident",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="report_purge_receipt",
                        to="incidents.incident",
                    ),
                ),
            ],
        ),
    ]
