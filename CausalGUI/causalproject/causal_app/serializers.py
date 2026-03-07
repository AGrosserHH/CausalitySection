from rest_framework import serializers


class EdgeInputSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=100)
    target = serializers.CharField(max_length=100)
    directed = serializers.BooleanField(required=False, default=True)


class SaveGraphRequestSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField(required=False)
    name = serializers.CharField(required=False, allow_blank=True, default="Unnamed Graph")
    edges = EdgeInputSerializer(many=True, required=False, default=list)


class CausalInferenceRequestSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    treatment = serializers.IntegerField()
    outcome = serializers.IntegerField()
    method_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class VariableItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class UploadCsvResponseSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    graph_name = serializers.CharField()
    variables = VariableItemSerializer(many=True)
    preview = serializers.ListField(child=serializers.DictField(), required=False)


class SaveGraphResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    graph_id = serializers.IntegerField()


class CausalInferenceResponseSerializer(serializers.Serializer):
    estimated_effect = serializers.FloatField()
    method_name = serializers.CharField()
    graph_image = serializers.CharField()
    estimand_string = serializers.CharField()


class OpenAISuggestEdgesRequestSerializer(serializers.Serializer):
    variables = serializers.ListField(
        child=serializers.CharField(max_length=100),
        min_length=2,
    )
    context = serializers.CharField(required=False, allow_blank=True, default="")
    max_edges = serializers.IntegerField(required=False, min_value=1, max_value=25, default=10)


class SuggestedEdgeSerializer(serializers.Serializer):
    source = serializers.CharField()
    target = serializers.CharField()
    directed = serializers.BooleanField(default=True)
    reason = serializers.CharField(required=False, allow_blank=True)


class OpenAISuggestEdgesResponseSerializer(serializers.Serializer):
    edges = SuggestedEdgeSerializer(many=True)
