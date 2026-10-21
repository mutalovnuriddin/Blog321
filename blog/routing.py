from django.urls import path

from .consumers import ChatConsumer, NotificationConsumer


websocket_urlpatterns = [
    path('ws/chat/<uuid:conversation_id>/', ChatConsumer.as_asgi()),
    path('ws/notify/', NotificationConsumer.as_asgi()),
]
