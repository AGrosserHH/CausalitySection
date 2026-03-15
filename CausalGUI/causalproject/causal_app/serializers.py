from rest_framework import serializers


class EdgeInputSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=100)
    target = serializers.CharField(max_length=100)
    directed = serializers.BooleanField(required=False, default=True)
    manual_lock = serializers.BooleanField(required=False, default=False)
    evidence = serializers.ListField(child=serializers.DictField(), required=False, default=list)


class NodePositionSerializer(serializers.Serializer):
    x = serializers.FloatField()
    y = serializers.FloatField()


class GraphNodeInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=100)
    position = NodePositionSerializer(required=False, allow_null=True)


class SaveGraphRequestSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField(required=False)
    name = serializers.CharField(required=False, allow_blank=True, default="Unnamed Graph")
    nodes = GraphNodeInputSerializer(many=True, required=False, default=list)
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


class GraphNodeDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    position = NodePositionSerializer(required=False, allow_null=True)


class GraphDetailsResponseSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    nodes = GraphNodeDetailSerializer(many=True, required=False, default=list)
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
    minimal_adjustment_sets = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField()),
        default=list,
    )
    iv_candidates = serializers.ListField(child=serializers.CharField(), required=False)
    frontdoor_variables = serializers.ListField(child=serializers.CharField(), required=False)
    overlap_ok = serializers.BooleanField()
    overlap_warnings = serializers.ListField(child=serializers.CharField(), default=list)
    badge = serializers.ChoiceField(choices=["trust", "caution", "reject"])
    reasons = serializers.ListField(child=serializers.CharField(), default=list)
    dag_valid = serializers.BooleanField(default=True)
    sample_size = serializers.IntegerField(required=False, default=0)
    treatment_variation = serializers.FloatField(required=False, allow_null=True)
    outcome_variation = serializers.FloatField(required=False, allow_null=True)
    graph_issues = serializers.ListField(child=serializers.CharField(), default=list)
    open_backdoor_paths = serializers.ListField(child=serializers.CharField(), default=list)
    blocked_paths = serializers.ListField(child=serializers.CharField(), default=list)
    admissibility_checklist = serializers.ListField(child=serializers.DictField(), default=list)


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
    confidence = serializers.FloatField(required=False, allow_null=True)
    recommended_action = serializers.CharField(required=False, allow_blank=True)
    verifier_breakdown = serializers.ListField(child=serializers.DictField(), default=list)
    evidence = EdgeEvidenceSerializer(many=True)


class OpenAIDraftGraphResponseSerializer(serializers.Serializer):
    edges = DraftedEdgeSerializer(many=True)
    confounder_candidates = serializers.ListField(child=serializers.CharField(), default=list)
    iv_candidates = serializers.ListField(child=serializers.CharField(), default=list)
    missing_confounder_hypotheses = serializers.ListField(child=serializers.CharField(), default=list)
    summary = serializers.DictField(required=False, default=dict)


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
    estimated_effect = serializers.FloatField(required=False, allow_null=True)
    delta = serializers.FloatField(required=False, allow_null=True)


class RobustnessDashboardResponseSerializer(serializers.Serializer):
    baseline_method = serializers.CharField(required=False, allow_blank=True)
    baseline_estimate = serializers.FloatField(required=False, allow_null=True)
    estimator_comparison = EstimatorComparisonItemSerializer(many=True)
    refutations = serializers.DictField(child=serializers.DictField())
    sensitivity = serializers.DictField(child=serializers.DictField())
    diagnostics = serializers.ListField(child=serializers.DictField(), default=list)
    sensitivity_points = serializers.ListField(child=serializers.DictField(), default=list)
    robustness_score = serializers.FloatField(required=False, allow_null=True)


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


class TimeSeriesAnalysisRequestSerializer(serializers.Serializer):
    graph_id = serializers.IntegerField()
    time_column = serializers.CharField(max_length=100)
    entity_column = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    window_count = serializers.IntegerField(required=False, min_value=2, max_value=12, default=4)
    max_lag = serializers.IntegerField(required=False, min_value=1, max_value=12, default=3)


class TimeSeriesEdgeStabilitySerializer(serializers.Serializer):
    source = serializers.CharField()
    target = serializers.CharField()
    best_lag = serializers.IntegerField(required=False, allow_null=True)
    mean_strength = serializers.FloatField()
    stability = serializers.FloatField()
    direction_consistency = serializers.FloatField()
    window_strengths = serializers.ListField(child=serializers.FloatField(), default=list)
    status = serializers.CharField()


class DynamicGraphEdgeSerializer(serializers.Serializer):
    source = serializers.CharField()
    target = serializers.CharField()
    strength = serializers.FloatField()
    best_lag = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.CharField()


class DynamicGraphWindowSerializer(serializers.Serializer):
    label = serializers.CharField()
    start = serializers.CharField()
    end = serializers.CharField()
    edges = DynamicGraphEdgeSerializer(many=True)


class TimeSeriesAnalysisResponseSerializer(serializers.Serializer):
    mode = serializers.CharField()
    time_column = serializers.CharField()
    entity_column = serializers.CharField(required=False, allow_blank=True)
    window_count = serializers.IntegerField()
    max_lag = serializers.IntegerField()
    edge_stability = TimeSeriesEdgeStabilitySerializer(many=True)
    dynamic_graphs = DynamicGraphWindowSerializer(many=True)
    diagnostics = serializers.ListField(child=serializers.DictField(), default=list)
