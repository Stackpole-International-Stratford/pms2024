# Generated by Django 4.1.3 on 2023-01-15 21:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('barcode', '0012_remove_lasermark_duplicate_scan_at_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lasermarkqualityscan',
            name='laser_mark',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='barcode.lasermark'),
        ),
    ]
