import pytest
from webtest import TestApp

from a2wsgi.asgi import ASGIMiddleware


async def hello_world(scope, receive, send):
    assert False
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"],],
        }
    )
    await send(
        {"type": "http.response.body", "body": b"Hello, world!",}
    )

@pytest.mark.asyncio
def test_asgi_get():
    app = ASGIMiddleware(hello_world)
    client = TestApp(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "Hello World!"
