from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0002_medicalreport_parser_message"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicalreport",
            name="parser_mode",
            field=models.CharField(max_length=50, blank=True),
        ),
    ]