from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0002_job_lease")]

    operations = [
        migrations.AlterField(
            model_name="logsource",
            name="parser_version",
            field=models.CharField(default="m2.2", max_length=32),
        ),
        migrations.AlterField(
            model_name="logevent",
            name="parser_version",
            field=models.CharField(default="m2.2", max_length=32),
        ),
    ]
