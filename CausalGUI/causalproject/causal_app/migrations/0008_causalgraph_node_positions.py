from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("causal_app", "0007_causaledge_manual_lock_edgeevidence"),
    ]

    operations = [
        migrations.AddField(
            model_name="causalgraph",
            name="node_positions",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]