# Generated by Django 4.2.13 on 2024-08-16 17:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quality', '0006_scrapform_tpc_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='feat',
            name='critical',
            field=models.BooleanField(default=False),
        ),
    ]
