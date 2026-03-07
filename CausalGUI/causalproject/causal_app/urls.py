from django.urls import path

from .views import (
    assess_query,
    causal_inference,
    get_variables,
    graph_details,
    openai_draft_graph,
    openai_suggest_edges,
    robustness_dashboard,
    root_cause_analysis,
    save_graph,
    upload_csv,
    what_if_analysis,
)

urlpatterns = [
    path('variables/', get_variables, name='variables'),
    path('save_graph/', save_graph, name='save_graph'),
    path('causal_inference/', causal_inference, name='causal_inference'),
    path('upload_csv/', upload_csv, name='upload_csv'),
    path('assess_query/', assess_query, name='assess_query'),
    path('assess-query/', assess_query, name='assess_query_alias_hyphen'),
    path('assess_query', assess_query, name='assess_query_alias_no_slash'),
    path('assess-query', assess_query, name='assess_query_alias_hyphen_no_slash'),
    path('graphs/<int:graph_id>/', graph_details, name='graph_details'),
    path('robustness_dashboard/', robustness_dashboard, name='robustness_dashboard'),
    path('what_if_analysis/', what_if_analysis, name='what_if_analysis'),
    path('root_cause_analysis/', root_cause_analysis, name='root_cause_analysis'),
    path('openai/suggest_edges/', openai_suggest_edges, name='openai_suggest_edges'),
    path('openai/draft_graph/', openai_draft_graph, name='openai_draft_graph'),
]

