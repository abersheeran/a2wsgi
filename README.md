# a2wsgi

Convert WSGI app to ASGI app.

## How to use

```python
from a2wsgi import WSGIMiddleware

ASGI_APP = WSGIMiddleware(WSGI_APP)
```
