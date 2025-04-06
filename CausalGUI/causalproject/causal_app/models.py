from django.db import models

class CausalGraph(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)    
    image_path = models.CharField(max_length=255, blank=True, null=True)
    data_file = models.FileField(upload_to='datasets/', null=True, blank=True)

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

    class Meta:
        unique_together = (('graph', 'source', 'target'),)

    def __str__(self):
        return f"{self.source.name} -> {self.target.name}"
