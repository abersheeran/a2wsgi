import io
import json

import httpx
import pytest

from a2wsgi import WSGIMiddleware


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks,sizes,pre_read",
    [
        ((b"ab", b"c\nrest"), (4, 4, 4), 0),
        ((b"ab", b"cd", b"ef\nrest"), (5, 3, 8), 1),
        ((b"", b"ab", b"", b"c\n"), (4, 4), 0),
        ((b"tail",), (20, 20), 0),
        ((b"abc\nxyz",), (0, 1, 4, -2, -1), 0),
        ((), (0, 4, -1), 0),
        ((b"abc\nrest",), (-1, -1, -1), 0),
    ],
)
async def test_wsgi_input_sized_readline(chunks, sizes, pre_read):
    reference = io.BytesIO(b"".join(chunks))
    expected = [reference.read(pre_read)]
    expected.extend(reference.readline(size) for size in sizes)
    expected.append(reference.read())

    def app(environ, start_response):
        stream = environ["wsgi.input"]
        result = [stream.read(pre_read)]
        result.extend(stream.readline(size) for size in sizes)
        result.append(stream.read())
        output = json.dumps([part.hex() for part in result]).encode()
        start_response("200 OK", [("Content-Length", str(len(output)))])
        return [output]

    async def content():
        for chunk in chunks:
            yield chunk

    middleware = WSGIMiddleware(app)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=middleware),
            base_url="http://testserver",
        ) as client:
            response = await client.post("/", content=content())
            assert response.status_code == 200
            assert response.json() == [part.hex() for part in expected]
    finally:
        middleware.executor.shutdown(wait=True)
