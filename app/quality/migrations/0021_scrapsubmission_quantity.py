# Generated by Django 4.2.23 on 2025-07-03 13:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quality', '0020_scrapsubmission'),
    ]

    operations = [
        migrations.AddField(
            model_name='scrapsubmission',
            name='quantity',
            field=models.PositiveIntegerField(default=1),
            preserve_default=False,
        ),
    ]
