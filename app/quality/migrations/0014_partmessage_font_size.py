# Generated by Django 4.2.15 on 2024-11-18 13:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quality', '0013_partmessage'),
    ]

    operations = [
        migrations.AddField(
            model_name='partmessage',
            name='font_size',
            field=models.CharField(choices=[('small', 'Small'), ('medium', 'Medium'), ('large', 'Large'), ('xl', 'Extra Large'), ('xxl', 'Double Extra Large'), ('xxxl', 'Triple Extra Large')], default='medium', max_length=10),
        ),
    ]