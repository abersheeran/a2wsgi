import asyncio
import threading
from enum import Enum
from http import HTTPStatus
from typing import cast, Iterable, Optional

from .types import (
    ExcInfo,
    Message,
    Scope,
    Environ,
    StartResponse,
    ASGIApp,
)

__all__ = ("ASGIMiddleware",)


def build_scope(environ: Environ) -> Scope:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "3.0"},
        "http_version": environ.get("SERVER_PROTOCOL", "http/1.0").split("/")[1],
        "method": environ["REQUEST_METHOD"],
        "scheme": environ.get("wsgi.url_scheme", "http"),
        "path": environ["PATH_INFO"].encode("latin1").decode("utf8"),
        "query_string": environ["QUERY_STRING"].encode("ascii"),
        "root_path": environ.get("SCRIPT_NAME", "").encode("latin1").decode("utf8"),
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

    wait_time: After the http response ends, the maximum time to wait for the ASGI app to run.
    """

    def __init__(
        self,
        app: ASGIApp,
        wait_time: float = None,
        loop: asyncio.AbstractEventLoop = None,
    ) -> None:
        self.app = app
        if loop is None:
            loop = asyncio.new_event_loop()
            loop_threading = threading.Thread(target=loop.run_forever, daemon=True)
            loop_threading.start()
        self.loop = loop
        self.wait_time = wait_time

    def __call__(
        self, environ: Environ, start_response: StartResponse
    ) -> Iterable[bytes]:
        return ASGIResponder(self.loop, self.app, wait_time=self.wait_time)(
            environ, start_response
        )


class ASGIState(Enum):
    RECEIVE = "R"
    SEND = "S"
    ERROR = "E"


class ASGIResponder:
    def __init__(
        self, loop: asyncio.AbstractEventLoop, app: ASGIApp, wait_time: float = None
    ) -> None:
        self.loop = loop
        self.app = app
        self.wait_time = wait_time
        self.sync_event = threading.Event()
        self.async_event: asyncio.Event
        self.loop.call_soon_threadsafe(self._init_async_event)
        self.state: Optional[ASGIState] = None
        self.body = bytearray()
        self.more_body = True
        self.exception: Optional[ExcInfo] = None
        self.asgi_msg: Optional[Message] = None

    def _done_callback(self, future: asyncio.Future) -> None:
        if future.exception():
            e = future.exception()
            self.exception = type(e), e, e.__traceback__
            self.state = ASGIState.ERROR
        self.sync_event.set()

    def _init_async_event(self) -> None:
        """
        Must init asyncio.Event in a loop.

        https://docs.python.org/3/library/asyncio-sync.html#asyncio.Event
        """
        if not hasattr(self, "async_event"):
            self.async_event = asyncio.Event()

    def __call__(
        self, environ: Environ, start_response: StartResponse
    ) -> Iterable[bytes]:
        scope = build_scope(environ)
        run_asgi: asyncio.Task = self.loop.create_task(
            self.app(scope, self.receive, self.send)
        )
        run_asgi.add_done_callback(self._done_callback)
        read_count, body = 0, environ["wsgi.input"]
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        self.more_body = content_length > 0
        self.loop.call_soon_threadsafe(lambda: None)  # call loop to run
        while True:  # do while
            self.sync_event.wait()
            self.sync_event.clear()
            if self.state == ASGIState.RECEIVE:
                data = body.read(min(16384, content_length - read_count))
                self.body.extend(data)
                read_count += len(data)
                self.more_body = read_count < content_length
            elif self.state == ASGIState.SEND:
                message = cast(Message, self.asgi_msg)
                self.asgi_msg = None
                if message["type"] == "http.response.start":
                    status = message["status"]
                    headers = [
                        (
                            name.strip().decode("latin1"),
                            value.strip().decode("latin1"),
                        )
                        for name, value in message["headers"]
                    ]
                    start_response(
                        f"{status} {HTTPStatus(status).phrase}", headers, None
                    )
                elif message["type"] == "http.response.body":
                    yield message.get("body", b"")
                    if not message.get("more_body", False):
                        break
                elif message["type"] == "http.response.disconnect":
                    break
                else:
                    run_asgi.cancel()
                    raise RuntimeError("What's wrong with the ASGI app?")
            elif self.state == ASGIState.ERROR:
                start_response(
                    f"{500} {HTTPStatus(500).phrase}",
                    [
                        ("Content-Type", "text/plain; charset=utf-8"),
                        ("Content-Length", str(len(HTTPStatus(500).description))),
                    ],
                    self.exception,
                )
                yield str(HTTPStatus(500).description).encode("utf-8")
                break

            if run_asgi.done() and self.state is None:
                break
            self.state = None
            self.loop.call_soon_threadsafe(
                lambda event: (event.set(), event.clear()), self.async_event
            )
        # HTTP response ends, wait for run_asgi's background tasks
        self.loop.call_soon_threadsafe(self.async_event.set)
        if not run_asgi.done():
            self.sync_event.wait(self.wait_time)
        run_asgi.cancel()

    async def receive(self) -> Message:
        if not self.more_body:
            return {"type": "http.request", "body": b"", "more_body": False}

        self.state = ASGIState.RECEIVE
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
        self.state = ASGIState.SEND
        self.asgi_msg = message
        self.sync_event.set()
        await self.async_event.wait()
