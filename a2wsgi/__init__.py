from .asgi import ASGIMiddleware
from .wsgi import WSGIMiddleware

VERSION = (1, 10, 5)

__version__: str = ".".join(map(str, VERSION))

__all__ = ("WSGIMiddleware", "ASGIMiddleware")
