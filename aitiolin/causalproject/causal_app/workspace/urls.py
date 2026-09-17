from django.urls import path
from .guard import guard
from . import views

urlpatterns = [
    path("session/", guard(views.session_info, "workspace_session")),
    path("session/data/", guard(views.delete_session, "workspace_delete")),
    path("samples/", guard(views.samples, "workspace_samples")),
    path("samples/<slug:sample_id>/load/", guard(views.load_sample, "workspace_load")),
    path("graphs/<int:graph_id>/runs/", guard(views.runs, "workspace_runs")),
    path("graphs/<int:graph_id>/image/", guard(views.graph_image, "workspace_image")),
    path("runs/<uuid:run_id>/bundle/", guard(views.bundle, "workspace_bundle")),
]
