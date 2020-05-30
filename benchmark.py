import time
import asyncio

import pytest
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
        if not message.get("more_body", False):
            break
        await send(
            {
                "type": "http.response.body",
                "body": message.get("body", b""),
                "more_body": True,
            }
        )
    await send({"type": "http.response.disconnect"})


def wsgi_echo(environ, start_response):
    status = "200 OK"
    body = environ["wsgi.input"].read()
    headers = [
        ("Content-Type", "text/plain; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    start_response(status, headers)
    return [body]


@pytest.mark.parametrize(
    "app, name",
    [
        (WSGIMiddleware(wsgi_echo), "a2wsgi-WSGIMiddleware"),
        (UvicornWSGIMiddleware(wsgi_echo), "uvicorn-WSGIMiddleware"),
        (WsgiToAsgi(wsgi_echo), "asgiref-WsgiToAsgi"),
    ],
)
@pytest.mark.asyncio
async def test_convert_wsgi_to_asgi(app, name):
    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        start_time = time.time()
        for _ in range(100):
            await client.post("/", data=b"hello world")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(10100):
            await client.post("/", data=b"hello world")
        time_count_100100 = time.time() - start_time
        print(
            f"\n{name} average duration: ",
            (time_count_100100 - time_count_100) / 10000,
            "second",
            end="",
        )


@pytest.mark.parametrize(
    "app, name", [(ASGIMiddleware(asgi_echo), "a2wsgi-ASGIMiddleware"),],
)
def test_convert_asgi_to_wsgi(app, name):
    with httpx.Client(app=app, base_url="http://testserver") as client:
        start_time = time.time()
        for _ in range(100):
            client.post("/", data=b"hello world")
        time_count_100 = time.time() - start_time
        start_time = time.time()
        for _ in range(10100):
            client.post("/", data=b"hello world")
        time_count_100100 = time.time() - start_time
        print(
            f"\n{name} average duration: ",
            (time_count_100100 - time_count_100) / 10000,
            "second",
            end="",
        )
