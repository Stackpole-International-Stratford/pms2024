# Generated by Django 4.1.3 on 2022-11-30 14:53

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('barcode', '0009_barcodepun_extended_part_number'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='barcodepun',
            name='extended_part_number',
        ),
    ]