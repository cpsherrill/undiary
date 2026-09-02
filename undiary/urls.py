from django.contrib import admin
from django.urls import include, path

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("sw.js", views.service_worker, name="service_worker"),
    path("offline", views.offline, name="offline"),
    path("todos", views.todos, name="todos"),
    path("todos/new", views.todo_create, name="todo_create"),
    path("todos/items/<int:pk>/toggle", views.todo_item_toggle, name="todo_item_toggle"),
    path("todos/<int:pk>/items", views.todo_item_add, name="todo_item_add"),
    path("todos/<int:pk>/note", views.todo_note, name="todo_note"),
    path("todos/<int:pk>/horizon", views.todo_horizon, name="todo_horizon"),
    path("todos/<int:pk>/<slug:action>", views.todo_verdict, name="todo_verdict"),
    path("audio/<int:pk>", views.entry_audio, name="entry_audio"),
    path("entries/<int:pk>", views.entry_detail, name="entry_detail"),
    path("entries/<int:pk>/star", views.entry_star, name="entry_star"),
    path("entries/<int:pk>/delete", views.entry_delete, name="entry_delete"),
    path("", views.index, name="index"),
]
