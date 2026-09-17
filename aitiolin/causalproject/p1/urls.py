from django.urls import path
from p0.guard import guard
from . import views

# P0 handles ownership/expiry/reservations. P1 records its own explicit specs,
# uses locally seeded generators and does not need the legacy global RNG lock.
urlpatterns=[
    path('schema/',guard(views.schema,'p0_p1_schema')),
    path('estimate/',guard(views.estimate,'p0_p1_estimate')),
    path('history/',guard(views.history,'p0_p1_history')),
    path('compare/',guard(views.compare,'p0_p1_compare')),
    path('bundles/preview/',guard(views.preview_restore,'p0_p1_preview')),
    path('bundles/restore/',guard(views.restore,'p0_p1_restore')),
    path('examples/<slug:sample_id>/load/',guard(views.load_synthetic,'p0_p1_example')),
]
