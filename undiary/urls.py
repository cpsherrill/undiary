from django.contrib import admin
from django.urls import include, path

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("audio/<int:pk>", views.entry_audio, name="entry_audio"),
    path("entries/<int:pk>", views.entry_detail, name="entry_detail"),
    path("entries/<int:pk>/delete", views.entry_delete, name="entry_delete"),
    path("", views.index, name="index"),
]
