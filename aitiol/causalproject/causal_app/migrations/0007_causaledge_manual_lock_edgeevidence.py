from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("causal_app", "0006_rename_knowledgegraphtrip_knowledgegraphtriple"),
    ]

    operations = [
        migrations.AddField(
            model_name="causaledge",
            name="manual_lock",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="EdgeEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "evidence_type",
                    models.CharField(
                        choices=[
                            ("semantic_prior", "Semantic Prior"),
                            ("ci_test", "Conditional Independence Evidence"),
                            ("score_search", "Score Search Support"),
                            ("temporal_prior", "Temporal Prior"),
                            ("manual", "Manual Lock"),
                            ("llm", "LLM Suggestion"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("supported", "Supported"),
                            ("weak", "Weak Support"),
                            ("rejected", "Rejected"),
                            ("conflict", "Conflict"),
                        ],
                        default="supported",
                        max_length=15,
                    ),
                ),
                ("score", models.FloatField(blank=True, null=True)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "edge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="evidences",
                        to="causal_app.causaledge",
                    ),
                ),
            ],
        ),
    ]
