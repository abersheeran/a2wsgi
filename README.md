# a2wsgi

Convert WSGI app to ASGI app or ASGI app to WSGI app.

Pure Python. No dependencies.

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

### Convert WSGI app to ASGI app

The performance of uvicorn-WSGIMiddleware is higher than a2wsgi. However, when dealing with large file uploads, it is easy to cause insufficient memory [uvicorn/issue#371](https://github.com/encode/uvicorn/issues/371). a2wsgi uses `asyncio.run_coroutine_threadsafe` to regulate the pace of reading data, thus solving this problem.

### Convert ASGI app to WSGI app

The HTTP trigger of Alibaba Cloud Serverless supports the WSGI interface but not the ASGI interface, which is very useful for deploying starlette/index.py to such services.
