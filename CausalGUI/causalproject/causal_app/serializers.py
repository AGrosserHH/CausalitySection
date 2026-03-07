from rest_framework import serializers


class EdgeInputSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=100)
    target = serializers.CharField(max_length=100)
    directed = serializers.BooleanField(required=False, default=True)
    manual_lock = serializers.BooleanField(required=False, default=False)
    evidence = serializers.ListField(child=serializers.DictField(), required=False, default=list)


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


class EdgeEvidenceSerializer(serializers.Serializer):
    evidence_type = serializers.CharField()
    status = serializers.CharField()
    score = serializers.FloatField(required=False, allow_null=True)
    details = serializers.DictField(required=False)


class GraphEdgeDetailSerializer(serializers.Serializer):
    source = serializers.CharField()
    target = serializers.CharField()
    directed = serializers.BooleanField(default=True)
    manual_lock = serializers.BooleanField(default=False)
    status = serializers.CharField(default="supported")
    evidence = EdgeEvidenceSerializer(many=True)


class GraphDetailsResponseSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    edges = GraphEdgeDetailSerializer(many=True)


class AssessQueryRequestSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    treatment = serializers.IntegerField()
    outcome = serializers.IntegerField()
    estimand = serializers.ChoiceField(choices=["ATE", "ATT", "ATC"], default="ATE")


class AssessQueryResponseSerializer(serializers.Serializer):
    identifiable = serializers.BooleanField()
    selected_estimand = serializers.CharField()
    suggested_method = serializers.CharField(allow_blank=True, required=False)
    adjustment_set = serializers.ListField(child=serializers.CharField(), required=False)
    iv_candidates = serializers.ListField(child=serializers.CharField(), required=False)
    frontdoor_variables = serializers.ListField(child=serializers.CharField(), required=False)
    overlap_ok = serializers.BooleanField()
    overlap_warnings = serializers.ListField(child=serializers.CharField(), default=list)
    badge = serializers.ChoiceField(choices=["trust", "caution", "reject"])
    reasons = serializers.ListField(child=serializers.CharField(), default=list)


class OpenAIDraftGraphRequestSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    context = serializers.CharField(required=False, allow_blank=True, default="")
    max_edges = serializers.IntegerField(required=False, min_value=1, max_value=25, default=10)


class DraftedEdgeSerializer(serializers.Serializer):
    source = serializers.CharField()
    target = serializers.CharField()
    directed = serializers.BooleanField(default=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    verification_status = serializers.ChoiceField(choices=["supported", "weak", "rejected", "conflict"])
    verification_score = serializers.FloatField(required=False, allow_null=True)
    evidence = EdgeEvidenceSerializer(many=True)


class OpenAIDraftGraphResponseSerializer(serializers.Serializer):
    edges = DraftedEdgeSerializer(many=True)
    confounder_candidates = serializers.ListField(child=serializers.CharField(), default=list)
    iv_candidates = serializers.ListField(child=serializers.CharField(), default=list)
    missing_confounder_hypotheses = serializers.ListField(child=serializers.CharField(), default=list)


class RobustnessDashboardRequestSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    treatment = serializers.IntegerField()
    outcome = serializers.IntegerField()
    estimators = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )


class EstimatorComparisonItemSerializer(serializers.Serializer):
    method_name = serializers.CharField()
    estimated_effect = serializers.FloatField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_blank=True)


class RefutationItemSerializer(serializers.Serializer):
    status = serializers.CharField()
    summary = serializers.CharField(required=False, allow_blank=True)
    p_value = serializers.FloatField(required=False, allow_null=True)


class RobustnessDashboardResponseSerializer(serializers.Serializer):
    baseline_method = serializers.CharField(required=False, allow_blank=True)
    estimator_comparison = EstimatorComparisonItemSerializer(many=True)
    refutations = serializers.DictField(child=serializers.DictField())
    sensitivity = serializers.DictField(child=serializers.DictField())


class WhatIfRequestSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    treatment = serializers.IntegerField()
    outcome = serializers.IntegerField()
    treatment_value = serializers.FloatField()


class WhatIfResponseSerializer(serializers.Serializer):
    baseline_outcome_mean = serializers.FloatField()
    baseline_treatment_mean = serializers.FloatField()
    estimated_ate = serializers.FloatField(required=False, allow_null=True)
    counterfactual_outcome_mean = serializers.FloatField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True)


class RootCauseRequestSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    outcome = serializers.IntegerField()


class AttributionItemSerializer(serializers.Serializer):
    variable = serializers.CharField()
    score = serializers.FloatField()
    details = serializers.CharField(required=False, allow_blank=True)


class RootCauseResponseSerializer(serializers.Serializer):
    anomaly_attribution = AttributionItemSerializer(many=True)
    distribution_change_attribution = AttributionItemSerializer(many=True)
