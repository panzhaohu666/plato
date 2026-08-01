"""
WebSocket URL routing for Plato.
"""
from django.urls import path
from apps.dynamic_models.consumers import YjsCollaborationConsumer


websocket_urlpatterns = [
    path(
        "ws/table/<str:table_name>/",
        YjsCollaborationConsumer.as_asgi(),
        name="ws-yjs-collaboration",
    ),
]
