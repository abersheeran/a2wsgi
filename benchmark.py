import time
import asyncio

import httpx
from a2wsgi import WSGIMiddleware, ASGIMiddleware

from uvicorn.middleware.wsgi import WSGIMiddleware as UvicornWSGIMiddleware
from asgiref.wsgi import WsgiToAsgi


async def asgi_hello_world(scope, receive, send):
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"],],
        }
    )
    await send(
        {"type": "http.response.body", "body": b"Hello, world!", "more_body": True}
    )
    await send({"type": "http.response.disconnect"})


def wsgi_hello_world(environ, start_response):
    status = "200 OK"
    output = b"Hello World!\n"
    headers = [
        ("Content-Type", "text/plain; charset=utf-8"),
        ("Content-Length", str(len(output))),
    ]
    start_response(status, headers)
    return [output]


async def wsgi_middleware():
    async with httpx.AsyncClient(
        app=WSGIMiddleware(wsgi_hello_world), base_url="http://testserver"
    ) as client:
        start_time = time.time()
        for _ in range(100):
            await client.get("/")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(100100):
            await client.get("/")
        time_count_100100 = time.time() - start_time
        print(
            "WSGIMiddleware average duration: ",
            (time_count_100100 - time_count_100) / 100000,
        )


def asgi_middleware():
    with httpx.Client(
        app=ASGIMiddleware(asgi_hello_world), base_url="http://testserver"
    ) as client:
        start_time = time.time()
        for _ in range(100):
            client.get("/")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(100100):
            client.get("/")
        time_count_100100 = time.time() - start_time
        print(
            "ASGIMiddleware average duration: ",
            (time_count_100100 - time_count_100) / 100000,
        )


async def uvicorn_wsgi_middleware():
    async with httpx.AsyncClient(
        app=UvicornWSGIMiddleware(wsgi_hello_world), base_url="http://testserver"
    ) as client:
        start_time = time.time()
        for _ in range(100):
            await client.get("/")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(100100):
            await client.get("/")
        time_count_100100 = time.time() - start_time
        print(
            "UvicornWSGIMiddleware average duration: ",
            (time_count_100100 - time_count_100) / 100000,
        )


async def wsgi_to_asgi():
    async with httpx.AsyncClient(
        app=WsgiToAsgi(wsgi_hello_world), base_url="http://testserver"
    ) as client:
        start_time = time.time()
        for _ in range(100):
            await client.get("/")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(100100):
            await client.get("/")
        time_count_100100 = time.time() - start_time
        print(
            "WsgiToAsgi average duration: ",
            (time_count_100100 - time_count_100) / 100000,
        )


if __name__ == "__main__":
    asgi_middleware()
    asyncio.run(uvicorn_wsgi_middleware())
    asyncio.run(wsgi_to_asgi())
    asyncio.run(wsgi_middleware())
