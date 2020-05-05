import asyncio
import threading
from http import HTTPStatus
from typing import Iterable, AnyStr

from .types import (
    Message,
    Scope,
    Environ,
    StartResponse,
    ASGIApp,
)

__all__ = ("ASGIMiddleware",)

global_loop = asyncio.new_event_loop()
threading.Thread(target=global_loop.run_forever, daemon=True, name="global_loop").start()


def build_scope(environ: Environ) -> Scope:
    scope = {
        "type": "http",
        "asgi": {"version": "2.1", "spec_version": "2.1",},
        "http_version": environ["SERVER_PROTOCOL"].split("/")[1],
        "method": environ["REQUEST_METHOD"],
        "scheme": environ.get("wsgi.url_scheme", "http"),
        "path": environ["PATH_INFO"],
        "query_string": environ["QUERY_STRING"].encode("ascii"),
        "root_path": environ.get("SCRIPT_NAME", ""),
        "client": None,
        "server": (environ["SERVER_NAME"], int(environ["SERVER_PORT"])),
    }
    headers = [
        (
            each[5:].lower().replace("_", "-").encode("latin1"),
            environ[each].encode("latin1"),
        )
        for each in environ.keys()
        if each.startswith("HTTP_")
    ]
    if environ.get("CONTENT_TYPE"):
        headers.append((b"content-type", environ["CONTENT_TYPE"].encode("latin1")))
    if environ.get("CONTENT_LENGTH"):
        headers.append((b"content-length", environ["CONTENT_LENGTH"].encode("latin1")))
    scope["headers"] = headers

    return scope


class ASGIMiddleware:
    """
    Convert ASGIApp to WSGIApp.
    """

    def __init__(
        self, app: ASGIApp, loop: asyncio.AbstractEventLoop = global_loop
    ) -> None:
        self.app = app
        self.loop = loop

    def __call__(
        self, environ: Environ, start_response: StartResponse
    ) -> Iterable[AnyStr]:
        return ASGIResponder(environ, start_response, self.loop)(self.app)


class ASGIResponder:
    def __init__(
        self,
        environ: Environ,
        start_response: StartResponse,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.environ = environ
        self.start_response = start_response
        self.loop = loop
        self.sync_event = threading.Event()
        self.async_event = asyncio.Event(loop=self.loop)
        self.body = bytearray()
        self.more_body = True
        self.exception = None
        self.resp_body = bytearray()
        self.more_resp_body = True

    def _done_callback(self, future: asyncio.Future) -> None:
        if future.exception():
            self.exception = future.exception()
            self.sync_event.set()
        self.more_resp_body = False

    def __call__(self, app: ASGIApp) -> Iterable[AnyStr]:
        scope = build_scope(self.environ)
        run_asgi: asyncio.Task = self.loop.create_task(
            app(scope, self.receive, self.send)
        )
        run_asgi.add_done_callback(self._done_callback)
        read_count, body = 0, self.environ["wsgi.input"]
        content_length = int(self.environ.get("CONTENT_LENGTH", 0))
        while read_count < content_length:
            self.sync_event.wait()
            if run_asgi.done():  # get a error
                self.start_response(f"500 {HTTPStatus(500).phrase}", [], self.exception)
                return [HTTPStatus(500).description]
            data = body.read(16384)
            self.body.extend(data)
            read_count += len(data)
            if read_count >= content_length:
                self.more_body = False
            self.async_event.set()

        while self.more_resp_body:
            self.async_event.set()
            self.sync_event.wait()
            yield bytes(self.resp_body)
            del self.resp_body[:]

    async def receive(self) -> Message:
        if not self.more_body:
            return {"type": "http.request", "body": b"", "more_body": False}

        self.sync_event.set()
        await self.async_event.wait()
        message = {
            "type": "http.request",
            "body": bytes(self.body),
            "more_body": self.more_body,
        }
        del self.body[:]
        return message

    async def send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            status = message["status"]
            headers = [
                (name.strip().decode("ascii").lower(), value.strip().decode("ascii"))
                for name, value in message["headers"]
            ]
            self.start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        elif message["type"] == "http.response.body":
            await self.async_event.wait()
            self.resp_body.extend(message.get("body", b""))
            self.more_resp_body = message.get("more_body", False)
            self.sync_event.set()
        elif message["type"] == "http.response.disconnect":
            self.more_resp_body = False
            self.sync_event.set()
