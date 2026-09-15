import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("causal_app", "0009_causalgraph_cleaned_file_causalgraph_cleaning_plan")]
    operations = [
        migrations.CreateModel(name="Workspace", fields=[
            ("token_hash", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("expires_at", models.DateTimeField(db_index=True)),
            ("busy", models.BooleanField(default=False)),
            ("deleting", models.BooleanField(default=False)),
        ]),
        migrations.CreateModel(name="GraphOwnership", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("sample_id", models.CharField(max_length=64, blank=True)),
            ("cleaning_history", models.JSONField(default=list)),
            ("graph", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                related_name="p0_owner", to="causal_app.causalgraph")),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                related_name="graphs", to="p0.workspace")),
        ]),
        migrations.CreateModel(name="Artifact", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("storage_name", models.CharField(max_length=500)),
            ("graph", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="causal_app.causalgraph")),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                related_name="artifacts", to="p0.workspace")),
        ], options={"constraints": [models.UniqueConstraint(fields=("workspace", "storage_name"), name="p0_unique_artifact")]}),
        migrations.CreateModel(name="RunRecord", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, editable=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("analysis_key", models.CharField(max_length=64, db_index=True)),
            ("operation", models.CharField(max_length=64)),
            ("payload", models.JSONField()),
            ("graph", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="causal_app.causalgraph")),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                related_name="runs", to="p0.workspace")),
        ]),
        migrations.CreateModel(name="LLMPermit", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, editable=False)),
            ("payload_hash", models.CharField(max_length=64)),
            ("operation", models.CharField(max_length=100)),
            ("expires_at", models.DateTimeField()),
            ("used", models.BooleanField(default=False)),
            ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="p0.workspace")),
        ]),
    ]
