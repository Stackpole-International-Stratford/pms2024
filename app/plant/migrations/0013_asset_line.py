# Generated by Django 4.2.15 on 2024-12-17 14:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plant', '0012_alter_questionairequestion_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='line',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
