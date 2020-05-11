import time
import asyncio

import httpx
from a2wsgi import WSGIMiddleware, ASGIMiddleware

from uvicorn.middleware.wsgi import WSGIMiddleware as UvicornWSGIMiddleware
from asgiref.wsgi import WsgiToAsgi


async def asgi_echo(scope, receive, send):
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"],],
        }
    )
    body = bytes()
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body", False):
            break
    await send({"type": "http.response.body", "body": body})


def wsgi_echo(environ, start_response):
    status = "200 OK"
    body = environ["wsgi.input"].read()
    headers = [
        ("Content-Type", "text/plain; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    start_response(status, headers)
    return [body]


async def wsgi_middleware():
    async with httpx.AsyncClient(
        app=WSGIMiddleware(wsgi_echo), base_url="http://testserver"
    ) as client:
        start_time = time.time()
        for _ in range(100):
            await client.post("/", data=b"hello world")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(100100):
            await client.post("/", data=b"hello world")
        time_count_100100 = time.time() - start_time
        print(
            "WSGIMiddleware average duration: ",
            (time_count_100100 - time_count_100) / 100000,
        )


def asgi_middleware():
    with httpx.Client(
        app=ASGIMiddleware(asgi_echo), base_url="http://testserver"
    ) as client:
        start_time = time.time()
        for _ in range(100):
            client.post("/", data=b"hello world")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(100100):
            client.post("/", data=b"hello world")
        time_count_100100 = time.time() - start_time
        print(
            "ASGIMiddleware average duration: ",
            (time_count_100100 - time_count_100) / 100000,
        )


async def uvicorn_wsgi_middleware():
    async with httpx.AsyncClient(
        app=UvicornWSGIMiddleware(wsgi_echo), base_url="http://testserver"
    ) as client:
        start_time = time.time()
        for _ in range(100):
            await client.post("/", data=b"hello world")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(100100):
            await client.post("/", data=b"hello world")
        time_count_100100 = time.time() - start_time
        print(
            "UvicornWSGIMiddleware average duration: ",
            (time_count_100100 - time_count_100) / 100000,
        )


async def wsgi_to_asgi():
    async with httpx.AsyncClient(
        app=WsgiToAsgi(wsgi_echo), base_url="http://testserver"
    ) as client:
        start_time = time.time()
        for _ in range(100):
            await client.post("/", data=b"hello world")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(100100):
            await client.post("/", data=b"hello world")
        time_count_100100 = time.time() - start_time
        print(
            "WsgiToAsgi average duration: ",
            (time_count_100100 - time_count_100) / 100000,
        )


if __name__ == "__main__":
    asyncio.run(uvicorn_wsgi_middleware())
    asyncio.run(wsgi_to_asgi())
    asyncio.run(wsgi_middleware())
    asgi_middleware()
