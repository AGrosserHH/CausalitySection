from django.urls import path
from causal_app.workspace.guard import guard
from . import views

# The workspace guard handles ownership/expiry/reservations. Comparisons record their own explicit specs,
# use locally seeded generators and do not need the legacy global RNG lock.
urlpatterns=[
    path('schema/',guard(views.schema,'workspace_analysis_schema')),
    path('estimate/',guard(views.estimate,'workspace_analysis_estimate')),
    path('history/',guard(views.history,'workspace_analysis_history')),
    path('compare/',guard(views.compare,'workspace_analysis_compare')),
    path('bundles/preview/',guard(views.preview_restore,'workspace_analysis_preview')),
    path('bundles/restore/',guard(views.restore,'workspace_analysis_restore')),
    path('examples/<slug:sample_id>/load/',guard(views.load_synthetic,'workspace_analysis_example')),
]
