import asyncio
from http import HTTPStatus
from io import BytesIO
from typing import Any, Optional

class Event:
    def __init__(self):
        self.__message = None
        self.__event = asyncio.Event()

    def set(self, message: Any) -> None:
        self.__message = message
        self.__event.set()

    async def wait(self) -> Any:
        await self.__event.wait()
        self.__event.clear()
        return self.__message

def build_scope(environ):
    headers = [
        (key.lower().replace("_", "-").encode(), value.encode())
        for key, value in environ.items()
        if key.startswith(("HTTP_", "CONTENT_"))
    ]
    
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": environ.get("SERVER_PROTOCOL", "http/1.0").split("/")[1],
        "method": environ["REQUEST_METHOD"],
        "scheme": environ.get("wsgi.url_scheme", "http"),
        "path": environ.get("PATH_INFO", ""),
        "query_string": environ.get("QUERY_STRING", "").encode(),
        "headers": headers,
    }

class ASGIMiddleware:
    def __init__(self, app, wait_time: Optional[float] = None):
        self.app = app
        self.wait_time = wait_time
        self.loop = asyncio.new_event_loop()

    def __call__(self, environ, start_response):
        receive_event = Event()
        send_event = Event()

        async def receive():
            return await receive_event.wait()

        async def send(message):
            await send_event.set(message)

        async def run_app():
            await self.app(build_scope(environ), receive, send)

        task = self.loop.create_task(run_app())
        body = environ.get("wsgi.input", BytesIO())
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        read_count = 0

        while not task.done():
            message = await send_event.wait()
            
            if message["type"] == "http.response.start":
                start_response(
                    f"{message['status']} {HTTPStatus(message['status']).phrase}",
                    [(k.decode(), v.decode()) for k, v in message["headers"]]
                )
            elif message["type"] == "http.response.body":
                yield message.get("body", b"")
                if not message.get("more_body", False):
                    break

            if read_count < content_length:
                data = body.read(min(65536, content_length - read_count))
                read_count += len(data)
                receive_event.set({
                    "type": "http.request",
                    "body": data,
                    "more_body": read_count < content_length
                })

        task.cancel()
        yield b""
