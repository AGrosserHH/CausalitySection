from django.urls import path
from .guard import guard
from . import views

urlpatterns = [
    path("session/", guard(views.session_info, "p0_session")),
    path("session/data/", guard(views.delete_session, "p0_delete")),
    path("samples/", guard(views.samples, "p0_samples")),
    path("samples/<slug:sample_id>/load/", guard(views.load_sample, "p0_load")),
    path("graphs/<int:graph_id>/runs/", guard(views.runs, "p0_runs")),
    path("graphs/<int:graph_id>/image/", guard(views.graph_image, "p0_image")),
    path("runs/<uuid:run_id>/bundle/", guard(views.bundle, "p0_bundle")),
]
