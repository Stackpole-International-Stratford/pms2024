# Generated by Django 4.2.13 on 2024-08-15 13:47

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('quality', '0002_scrapform_alter_feat_order_featentry'),
    ]

    operations = [
        migrations.AddField(
            model_name='featentry',
            name='partNumber',
            field=models.CharField(default=django.utils.timezone.now, max_length=256),
            preserve_default=False,
        ),
    ]