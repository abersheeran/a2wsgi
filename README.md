# a2wsgi

Convert WSGI app to ASGI app or ASGI app to WSGI app.

Pure Python. No dependencies. High performance.

## Install

```
pip install a2wsgi
```

## How to use

Convert WSGI app to ASGI app:

```python
from a2wsgi import WSGIMiddleware

ASGI_APP = WSGIMiddleware(WSGI_APP)
```

Convert ASGI app to WSGI app:

```python
from a2wsgi import ASGIMiddleware

WSGI_APP = ASGIMiddleware(ASGI_APP)
```
