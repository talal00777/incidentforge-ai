from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="ingestionjob",
            name="claim_token",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ingestionjob",
            name="lease_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
