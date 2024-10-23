# Generated by Django 4.2.13 on 2024-10-04 17:48

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('forms', '0003_remove_formquestionanswer_answer_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='FormAnswer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('answer', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='FormQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', models.JSONField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('form', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions', to='forms.form')),
            ],
        ),
        migrations.DeleteModel(
            name='FormQuestionAnswer',
        ),
        migrations.AddField(
            model_name='formanswer',
            name='question',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='forms.formquestion'),
        ),
    ]