import asyncio
import collections
import threading
from http import HTTPStatus
from typing import Any, Iterable, Deque

from .types import (
    Message,
    Scope,
    Environ,
    StartResponse,
    ASGIApp,
)

__all__ = ("ASGIMiddleware",)


class AsyncEvent:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.__waiters: Deque[asyncio.Future] = collections.deque()
        self.__nowait = False

    def _set(self, message: Any) -> None:
        for future in self.__waiters:  # type: asyncio.Future
            if future.done():
                continue
            future.set_result(message)

    def set(self, message: Any) -> None:
        self.loop.call_soon_threadsafe(self._set, message)

    async def wait(self) -> Any:
        if self.__nowait:
            return None

        future = self.loop.create_future()
        self.__waiters.append(future)
        try:
            result = await future
            return result
        finally:
            self.__waiters.remove(future)

    def set_nowait(self) -> None:
        self.__nowait = True


class SyncEvent:
    def __init__(self) -> None:
        self.__event = threading.Event()
        self.__message: Any = None

    def set(self, message: Any) -> None:
        self.__message = message
        self.__event.set()

    def wait(self) -> Any:
        self.__event.wait()
        self.__event.clear()
        message, self.__message = self.__message, None
        return message


def build_scope(environ: Environ) -> Scope:
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

    return {
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
        "headers": headers,
    }


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


class ASGIResponder:
    def __init__(
        self, loop: asyncio.AbstractEventLoop, app: ASGIApp, wait_time: float = None
    ) -> None:
        self.loop = loop
        self.app = app
        self.wait_time = wait_time

        self.sync_event = SyncEvent()
        self.async_event = AsyncEvent(loop)

    def __call__(
        self, environ: Environ, start_response: StartResponse
    ) -> Iterable[bytes]:

        asgi_done = threading.Event()

        def _done_callback(future: asyncio.Future) -> None:
            if future.exception() is not None:
                e: BaseException = future.exception()  # type: ignore
                self.sync_event.set(
                    {"type": "error", "exception": (type(e), e, e.__traceback__)}
                )
            asgi_done.set()

        run_asgi: asyncio.Task = self.loop.create_task(
            self.app(build_scope(environ), self.receive, self.send)
        )
        run_asgi.add_done_callback(_done_callback)

        read_count, body = 0, environ["wsgi.input"]
        content_length = int(environ.get("CONTENT_LENGTH", None) or 0)

        self.loop.call_soon_threadsafe(lambda: None)

        while True:
            message = self.sync_event.wait()
            message_type = message["type"]
            if message_type == "receive":
                data = body.read(min(16384, content_length - read_count))
                read_count += len(data)
                self.async_event.set(
                    {
                        "type": "http.request",
                        "body": data,
                        "more_body": read_count < content_length,
                    }
                )
            elif message_type == "http.response.start":
                status = message["status"]
                headers = [
                    (
                        name.strip().decode("latin1"),
                        value.strip().decode("latin1"),
                    )
                    for name, value in message["headers"]
                ]
                start_response(f"{status} {HTTPStatus(status).phrase}", headers, None)
                self.async_event.set(None)
            elif message_type == "http.response.body":
                yield message.get("body", b"")
                more_body = message.get("more_body", False)
                if not more_body:
                    self.async_event.set_nowait()
                self.async_event.set(None)
                if not more_body:
                    break
            elif message_type == "http.response.disconnect":
                self.async_event.set_nowait()
                self.async_event.set(None)
                break
            elif message_type == "error":
                try:
                    raise message["exception"][0].with_traceback(
                        message["exception"][1], message["exception"][2]
                    )
                except message["exception"][0]:
                    start_response(
                        f"{500} {HTTPStatus(500).phrase}",
                        [
                            ("Content-Type", "text/plain; charset=utf-8"),
                            ("Content-Length", str(len(HTTPStatus(500).description))),
                        ],
                        message["exception"],
                    )
                    yield str(HTTPStatus(500).description).encode("utf-8")
                    self.async_event.set_nowait()
                    self.async_event.set(None)
                    break

            if run_asgi.done():
                break

        # HTTP response ends, wait for run_asgi's background tasks
        asgi_done.wait(self.wait_time)
        run_asgi.cancel()
        yield b""

    async def receive(self) -> Message:
        self.sync_event.set({"type": "receive"})
        return await self.async_event.wait()

    async def send(self, message: Message) -> None:
        self.sync_event.set(message)
        await self.async_event.wait()
