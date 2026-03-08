from django.db import models

class CausalGraph(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)    
    image_path = models.CharField(max_length=255, blank=True, null=True)
    data_file = models.FileField(upload_to='datasets/', null=True, blank=True)
    node_positions = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name

class Variable(models.Model):
    name = models.CharField(max_length=100)
    graph = models.ForeignKey(CausalGraph, related_name='variables', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('graph', 'name')

class CausalEdge(models.Model):
    graph = models.ForeignKey(CausalGraph, related_name='edges', on_delete=models.CASCADE)
    source = models.ForeignKey(Variable, related_name='source_edges', on_delete=models.CASCADE)
    target = models.ForeignKey(Variable, related_name='target_edges', on_delete=models.CASCADE)
    directed = models.BooleanField(default=True)
    manual_lock = models.BooleanField(default=False)

    class Meta:
        unique_together = (('graph', 'source', 'target'),)

    def __str__(self):
        return f"{self.source.name} -> {self.target.name}"


class EdgeEvidence(models.Model):
    EVIDENCE_TYPE_CHOICES = [
        ("semantic_prior", "Semantic Prior"),
        ("ci_test", "Conditional Independence Evidence"),
        ("score_search", "Score Search Support"),
        ("temporal_prior", "Temporal Prior"),
        ("manual", "Manual Lock"),
        ("llm", "LLM Suggestion"),
    ]

    STATUS_CHOICES = [
        ("supported", "Supported"),
        ("weak", "Weak Support"),
        ("rejected", "Rejected"),
        ("conflict", "Conflict"),
    ]

    edge = models.ForeignKey(CausalEdge, related_name="evidences", on_delete=models.CASCADE)
    evidence_type = models.CharField(max_length=30, choices=EVIDENCE_TYPE_CHOICES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="supported")
    score = models.FloatField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.edge} [{self.evidence_type}:{self.status}]"

class KnowledgeGraph(models.Model):
    name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class KnowledgeGraphTriple(models.Model):
    graph = models.ForeignKey(KnowledgeGraph, related_name="triples", on_delete=models.CASCADE)
    subject = models.TextField()
    predicate = models.TextField()
    object = models.TextField()