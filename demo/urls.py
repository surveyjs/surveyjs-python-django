"""Demo only: the Data panel's read-back, GET /demo/stored/<slug> (demo/views.py)."""

from django.urls import path

from demo import views

urlpatterns = [
    path("demo/stored/<slug:slug>", views.stored),
]
