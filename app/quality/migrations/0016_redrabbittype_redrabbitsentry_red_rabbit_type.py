# Generated by Django 4.2.15 on 2024-11-22 14:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quality', '0015_redrabbitsentry'),
    ]

    operations = [
        migrations.CreateModel(
            name='RedRabbitType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
            ],
        ),
        migrations.AddField(
            model_name='redrabbitsentry',
            name='red_rabbit_type',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='quality.redrabbittype'),
        ),
    ]
