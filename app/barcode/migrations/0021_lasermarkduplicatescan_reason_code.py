# Generated by Django 4.2.11 on 2024-03-13 17:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('barcode', '0020_remove_barcodepun_parts_per_layer_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='lasermarkduplicatescan',
            name='reason_code',
            field=models.IntegerField(default=0),
        ),
    ]
