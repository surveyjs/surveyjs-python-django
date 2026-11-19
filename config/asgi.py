"""
ASGI config for config project: what uvicorn serves (`python manage.py serve`).

It exposes the ASGI callable as a module-level variable named ``application``: Django for HTTP and the two relays
(Channels consumers) for WebSockets, on one port. Around them, outermost first: the lifespan (the demo's sandbox
pruner, closing the HTTP client), the request size limit, and (demo only, DEMO_MODE) the visitor's sandbox.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Django first: the consumers and the middleware below import models
django_application = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from config.body_limit import BodyLimit  # noqa: E402
from config.lifespan import Lifespan  # noqa: E402
from demo.sandbox import DemoSandbox  # noqa: E402
from demo.users import DemoUserWebSocketMiddleware  # noqa: E402
from examples.routing import websocket_urlpatterns  # noqa: E402

application = Lifespan(BodyLimit(DemoSandbox(ProtocolTypeRouter({
    'http': django_application,
    # Demo only: DemoUserWebSocketMiddleware sets scope["user"] from the demo_user cookie; a real app uses
    # channels.auth.AuthMiddlewareStack with Django's sessions
    'websocket': DemoUserWebSocketMiddleware(URLRouter(websocket_urlpatterns)),
}))))
