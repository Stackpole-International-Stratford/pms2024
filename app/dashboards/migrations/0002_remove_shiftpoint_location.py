# Generated by Django 4.2.13 on 2024-07-08 18:08

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboards', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='shiftpoint',
            name='location',
        ),
    ]
