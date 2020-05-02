# a2wsgi

Convert WSGI app to ASGI app. Pure Python. No dependencies. High performance.

## Install

```
pip install a2wsgi
```

## How to use

```python
from a2wsgi import WSGIMiddleware

ASGI_APP = WSGIMiddleware(WSGI_APP)
```
