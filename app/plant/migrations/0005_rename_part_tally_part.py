# Generated by Django 4.2.18 on 2025-02-12 13:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quality', '0023_qualitytag'),
        ('plant', '0004_asset_asset_name_part_part_name'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Part',
            new_name='Tally_Part',
        ),
    ]
