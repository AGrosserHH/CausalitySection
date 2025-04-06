# Generated by Django 5.1.4 on 2025-04-06 10:09

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("causal_app", "0003_causalgraph_data_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="variable",
            name="graph",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="variables",
                to="causal_app.causalgraph",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="variable",
            name="name",
            field=models.CharField(max_length=100),
        ),
        migrations.AlterUniqueTogether(
            name="variable",
            unique_together={("graph", "name")},
        ),
    ]
