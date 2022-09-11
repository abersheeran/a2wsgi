"""
**Need Python3.7+**
"""
import asyncio
import time

import httpx
import pytest
from asgiref.wsgi import WsgiToAsgi
from uvicorn.middleware.wsgi import WSGIMiddleware as UvicornWSGIMiddleware

from a2wsgi import ASGIMiddleware, WSGIMiddleware

try:
    import uvloop

    uvloop.install()
except ImportError:
    pass


async def asgi_echo(scope, receive, send):
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )

    while True:
        message = await receive()
        more_body = message.get("more_body", False)
        await send(
            {
                "type": "http.response.body",
                "body": message.get("body", b""),
                "more_body": more_body,
            }
        )
        if not more_body:
            break


def wsgi_echo(environ, start_response):
    status = "200 OK"
    body = environ["wsgi.input"].read()
    headers = [
        ("Content-Type", "text/plain; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    start_response(status, headers)
    return [body]


@pytest.fixture(scope="module", autouse=True)
def print_title():
    print(f"\n{'Name':^30}", "Average Time", end="", flush=True)


@pytest.mark.parametrize(
    "app, name",
    [
        (asgi_echo, "pure-ASGI"),
        (WSGIMiddleware(wsgi_echo), "a2wsgi-WSGIMiddleware"),
        (UvicornWSGIMiddleware(wsgi_echo), "uvicorn-WSGIMiddleware"),
        (WsgiToAsgi(wsgi_echo), "asgiref-WsgiToAsgi"),
    ],
)
@pytest.mark.asyncio
async def test_convert_wsgi_to_asgi(app, name):
    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        start_time = time.time_ns()
        await asyncio.gather(
            *[client.post("/", content=b"hello world") for _ in range(100)]
        )
        time_count_100 = time.time_ns() - start_time
        start_time = time.time_ns()
        await asyncio.gather(
            *[client.post("/", content=b"hello world") for _ in range(10100)]
        )
        time_count_100100 = time.time_ns() - start_time
        print(
            f"\n{name:^30}",
            (time_count_100100 - time_count_100) / 10000 / 10**9,
            end="",
        )


@pytest.mark.parametrize(
    "app, name",
    [(wsgi_echo, "pure-WSGI"), (ASGIMiddleware(asgi_echo), "a2wsgi-ASGIMiddleware")],
)
def test_convert_asgi_to_wsgi(app, name):
    with httpx.Client(app=app, base_url="http://testserver") as client:
        start_time = time.time_ns()
        for _ in range(100):
            client.post("/", content=b"hello world")
        time_count_100 = time.time_ns() - start_time
        start_time = time.time_ns()
        for _ in range(10100):
            client.post("/", content=b"hello world")
        time_count_100100 = time.time_ns() - start_time
        print(
            f"\n{name:^30}",
            (time_count_100100 - time_count_100) / 10000 / 10**9,
            end="",
        )
