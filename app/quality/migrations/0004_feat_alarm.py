# Generated by Django 4.2.13 on 2024-08-15 14:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quality', '0003_featentry_partnumber'),
    ]

    operations = [
        migrations.AddField(
            model_name='feat',
            name='alarm',
            field=models.IntegerField(default=0),
        ),
    ]
