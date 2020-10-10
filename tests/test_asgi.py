import httpx
import pytest

from a2wsgi.asgi import ASGIMiddleware


async def hello_world(scope, receive, send):
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/plain"],
            ],
        }
    )
    await send(
        {"type": "http.response.body", "body": b"Hello, world!", "more_body": True}
    )
    await send({"type": "http.response.disconnect"})


async def echo_body(scope, receive, send):
    assert scope["type"] == "http"
    body = b""
    more_body = True
    while more_body:
        msg = await receive()
        body += msg.get("body", b"")
        more_body = msg.get("more_body", False)
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"Content-Length", str(len(body)).encode("latin1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def raise_exception(scope, receive, send):
    raise RuntimeError("Something went wrong")


def test_asgi_get():
    app = ASGIMiddleware(hello_world)
    with httpx.Client(app=app, base_url="http://testserver:80") as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.text == "Hello, world!"


def test_asgi_post():
    app = ASGIMiddleware(echo_body)
    with httpx.Client(app=app, base_url="http://testserver:80") as client:
        response = client.post("/", data="hi boy")
        assert response.status_code == 200
        assert response.text == "hi boy"


def test_asgi_exception():
    app = ASGIMiddleware(raise_exception)
    with httpx.Client(app=app, base_url="http://testserver:80") as client:
        with pytest.raises(RuntimeError):
            client.get("/")
