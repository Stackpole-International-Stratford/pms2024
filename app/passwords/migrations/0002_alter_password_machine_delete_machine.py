# Generated by Django 4.2.13 on 2024-08-02 12:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('passwords', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='password',
            name='machine',
            field=models.CharField(max_length=100),
        ),
        migrations.DeleteModel(
            name='Machine',
        ),
    ]
