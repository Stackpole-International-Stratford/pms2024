# Generated by Django 4.2.13 on 2024-07-08 14:32

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ShiftPoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tv_number', models.IntegerField()),
                ('location', models.CharField(max_length=100)),
                ('points', models.JSONField(default=list)),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
