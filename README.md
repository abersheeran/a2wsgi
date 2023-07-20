# a2wsgi

Convert WSGI app to ASGI app or ASGI app to WSGI app.

Pure Python. Only depend on the standard library.

Compared with other converters, the advantage is that a2wsgi will not accumulate the requested content or response content in the memory, so you don't have to worry about the memory limit caused by a2wsgi. This problem exists in converters implemented by uvicorn/startlette or hypercorn.

## Install

```
pip install a2wsgi
```

## How to use

### `WSGIMiddleware`

Convert WSGI app to ASGI app:

```python
from a2wsgi import WSGIMiddleware

ASGI_APP = WSGIMiddleware(WSGI_APP)
```

WSGIMiddleware executes WSGI applications with a thread pool of up to 10 threads by default. If you want to increase or decrease this number, just like `WSGIMiddleware(..., workers=15)`.

### `ASGIMiddleware`

Convert ASGI app to WSGI app:

```python
from a2wsgi import ASGIMiddleware

WSGI_APP = ASGIMiddleware(ASGI_APP)
```

`ASGIMiddleware` will wait for the ASGI application's Background Task to complete before returning the last null byte. But sometimes you may not want to wait indefinitely for the execution of the Background Task of the ASGI application, then you only need to give the parameter `ASGIMiddleware(..., wait_time=5.0)`, after the time exceeds, the ASGI task corresponding to the request will be tried to cancel, and the last null byte will be returned.

You can also specify your own event loop through the `loop` parameter instead of the default event loop. Like `ASGIMiddleware(..., loop=faster_loop)`

### Access the original `Scope`/`Environ`

Sometimes you may need to access the original WSGI Environ in the ASGI application, just use `scope["wsgi_environ"]`; it is also easy to access the ASGI Scope in the WSGI Application, use `environ["asgi.scope"]`.

## Benchmark

Run `pytest ./benchmark.py -s` to compare the performance of `a2wsgi` and `uvicorn.middleware.wsgi.WSGIMiddleware` / `asgiref.wsgi.WsgiToAsgi`.

## Why a2wsgi

### Convert WSGI app to ASGI app

You can convert an existing WSGI project to an ASGI project to make it easier to migrate from WSGI applications to ASGI applications.

### Convert ASGI app to WSGI app

There is a lot of support for WSGI. Converting ASGI to WSGI, you will be able to use many existing services to deploy ASGI applications.
