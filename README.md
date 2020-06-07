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

## Benchmark

Run `pytest ./benchmark.py -s` to compare the performance of `a2wsgi` and `uvicorn.middleware.wsgi.WSGIMiddleware` / `asgiref.wsgi.WsgiToAsgi`.

## Why a2wsgi

The performance of uvicorn-WSGIMiddleware is higher than a2wsgi. However, when dealing with large file uploads, it is easy to cause insufficient memory [uvicorn/issue#371](https://github.com/encode/uvicorn/issues/371). a2wsgi uses synchronous signals and asynchronous signals to regulate the pace of reading data, thus solving this problem.

With the help of `ASGIMiddleware`, you can turn any ASGI program into a WSGI program. This is very effective when deploying starlette, FastAPI, responder, index.py to Serverless.
