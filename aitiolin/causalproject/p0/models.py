import uuid
from django.db import models


class Workspace(models.Model):
    # Only a SHA-256 digest is persisted; the random bearer secret stays in the tab.
    token_hash = models.CharField(max_length=64, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    busy = models.BooleanField(default=False)
    deleting = models.BooleanField(default=False)


class GraphOwnership(models.Model):
    graph = models.OneToOneField("causal_app.CausalGraph", on_delete=models.CASCADE,
                                related_name="p0_owner")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="graphs")
    sample_id = models.CharField(max_length=64, blank=True)
    cleaning_history = models.JSONField(default=list)


class Artifact(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="artifacts")
    graph = models.ForeignKey("causal_app.CausalGraph", on_delete=models.CASCADE)
    storage_name = models.CharField(max_length=500)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "storage_name"],
                                              name="p0_unique_artifact")]


class RunRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="runs")
    graph = models.ForeignKey("causal_app.CausalGraph", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    analysis_key = models.CharField(max_length=64, db_index=True)
    operation = models.CharField(max_length=64)
    payload = models.JSONField()


class LLMPermit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    payload_hash = models.CharField(max_length=64)
    operation = models.CharField(max_length=100)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
