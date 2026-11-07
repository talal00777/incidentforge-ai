import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def enforce_postgres_immutability(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE FUNCTION inv_postmortem_read_only() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Postmortem versions are immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    schema_editor.execute(
        """
        CREATE TRIGGER inv_postmortem_no_update
        BEFORE UPDATE ON investigations_postmortemversion
        FOR EACH ROW EXECUTE FUNCTION inv_postmortem_read_only();
        """
    )


def remove_postgres_immutability(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS inv_postmortem_no_update ON investigations_postmortemversion;"
    )
    schema_editor.execute("DROP FUNCTION IF EXISTS inv_postmortem_read_only();")


class Migration(migrations.Migration):
    dependencies = [
        ("investigations", "0002_human_review"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PostmortemVersion",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("version", models.PositiveIntegerField()),
                ("schema_version", models.CharField(default="1.0", max_length=12)),
                ("content", models.JSONField()),
                ("content_sha256", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "incident",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="postmortem_versions",
                        to="incidents.incident",
                    ),
                ),
                (
                    "investigation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="postmortem_versions",
                        to="investigations.investigationreport",
                    ),
                ),
                (
                    "review_revision",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="postmortem_versions",
                        to="investigations.investigationreviewrevision",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-version",)},
        ),
        migrations.AddIndex(
            model_name="postmortemversion",
            index=models.Index(fields=["incident", "-version"], name="inv_pm_inc_ver_idx"),
        ),
        migrations.AddConstraint(
            model_name="postmortemversion",
            constraint=models.UniqueConstraint(
                fields=("incident", "version"), name="inv_pm_inc_version_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="postmortemversion",
            constraint=models.UniqueConstraint(
                fields=("investigation", "review_revision"), name="inv_pm_report_review_uniq"
            ),
        ),
        migrations.RunPython(
            enforce_postgres_immutability, reverse_code=remove_postgres_immutability
        ),
    ]
