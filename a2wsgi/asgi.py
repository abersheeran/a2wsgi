import asyncio
import collections
import threading
from http import HTTPStatus
from io import BytesIO
from itertools import chain
from typing import Any, Coroutine, Deque, Iterable, Optional
from typing import cast as typing_cast

from .types import ASGIApp, Environ, ExcInfo, Message, Scope, StartResponse


class defaultdict(dict):
    def __init__(self, default_factory, *args, **kwargs) -> None:
        self.default_factory = default_factory
        super().__init__(*args, **kwargs)

    def __missing__(self, key):
        return self.default_factory(key)


StatusStringMapping = defaultdict(
    lambda status: f"{status} Unknown Status Code",
    {int(status): f"{status} {status.phrase}" for status in HTTPStatus},
)


class AsyncEvent:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.__waiters: Deque[asyncio.Future] = collections.deque()
        self.__nowait = False

    def _set(self, message: Any) -> None:
        for future in filter(lambda f: not f.done(), self.__waiters):
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
        self.__write_event = threading.Event()
        self.__message: Any = None

    def set(self, message: Any) -> None:
        self.__message = message
        self.__write_event.set()

    def wait(self) -> Any:
        self.__write_event.wait()
        self.__write_event.clear()
        message, self.__message = self.__message, None
        return message


def build_scope(environ: Environ) -> Scope:
    headers = [
        (key.lower().replace("_", "-").encode("latin-1"), value.encode("latin-1"))
        for key, value in chain(
            (
                (key[5:], value)
                for key, value in environ.items()
                if key.startswith("HTTP_")
                and key not in ("HTTP_CONTENT_TYPE", "HTTP_CONTENT_LENGTH")
            ),
            (
                (key, value)
                for key, value in environ.items()
                if key in ("CONTENT_TYPE", "CONTENT_LENGTH")
            ),
        )
    ]

    if environ.get("REMOTE_ADDR") and environ.get("REMOTE_PORT"):
        client = (environ["REMOTE_ADDR"], int(environ["REMOTE_PORT"]))
    else:
        client = None

    return {
        "wsgi_environ": environ,
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "3.0"},
        "http_version": environ.get("SERVER_PROTOCOL", "http/1.0").split("/")[1],
        "method": environ["REQUEST_METHOD"],
        "scheme": environ.get("wsgi.url_scheme", "http"),
        "path": environ["PATH_INFO"].encode("latin1").decode("utf8"),
        "query_string": environ["QUERY_STRING"].encode("ascii"),
        "root_path": environ.get("SCRIPT_NAME", "").encode("latin1").decode("utf8"),
        "client": client,
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
        wait_time: Optional[float] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
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
        return ASGIResponder(self.app, self.loop, self.wait_time)(
            environ, start_response
        )


class ASGIResponder:
    def __init__(
        self,
        app: ASGIApp,
        loop: asyncio.AbstractEventLoop,
        wait_time: Optional[float] = None,
    ) -> None:
        self.app = app
        self.loop = loop
        self.wait_time = wait_time

        self.sync_event = SyncEvent()
        self.async_event = AsyncEvent(loop)
        self.async_lock: asyncio.Lock

        def _init_async_lock():
            self.async_lock = asyncio.Lock()

        loop.call_soon_threadsafe(_init_async_lock)

        self.asgi_done = threading.Event()
        self.wsgi_should_stop: bool = False

    async def asgi_receive(self) -> Message:
        async with self.async_lock:
            self.sync_event.set({"type": "receive"})
            return await self.async_event.wait()

    async def asgi_send(self, message: Message) -> None:
        async with self.async_lock:
            self.sync_event.set(message)
            await self.async_event.wait()

    def asgi_done_callback(self, future: asyncio.Future) -> None:
        exception = future.exception()
        if exception is not None:
            self.sync_event.set(
                {
                    "type": "a2wsgi.error",
                    "exception": (
                        type(exception),
                        exception,
                        exception.__traceback__,
                    ),
                }
            )
        self.asgi_done.set()

    def start_asgi_app(self, environ: Environ) -> asyncio.Task:
        run_asgi: asyncio.Task = self.loop.create_task(
            typing_cast(
                Coroutine[None, None, None],
                self.app(build_scope(environ), self.asgi_receive, self.asgi_send),
            )
        )
        run_asgi.add_done_callback(self.asgi_done_callback)
        return run_asgi

    def __call__(
        self, environ: Environ, start_response: StartResponse
    ) -> Iterable[bytes]:
        read_count: int = 0
        body = environ["wsgi.input"] or BytesIO()
        content_length = int(environ.get("CONTENT_LENGTH", None) or 0)

        asgi_task = self.start_asgi_app(environ)
        # activate loop
        self.loop.call_soon_threadsafe(lambda: None)

        while True:
            message = self.sync_event.wait()
            message_type = message["type"]

            if message_type == "http.response.start":
                start_response(
                    StatusStringMapping[message["status"]],
                    [
                        (
                            name.strip().decode("latin1"),
                            value.strip().decode("latin1"),
                        )
                        for name, value in message["headers"]
                    ],
                    None,
                )
            elif message_type == "http.response.body":
                yield message.get("body", b"")
                self.wsgi_should_stop = not message.get("more_body", False)
            elif message_type == "http.response.disconnect":
                self.wsgi_should_stop = True
            # ASGI application error
            elif message_type == "a2wsgi.error":
                yield from self.error_response(start_response, message["exception"])
                self.wsgi_should_stop = True

            if message_type == "receive":
                data: bytes = body.read(min(65536, content_length - read_count))
                read_count += len(data)
                self.async_event.set(
                    {
                        "type": "http.request",
                        "body": data,
                        "more_body": read_count < content_length,
                    }
                )
            else:
                self.async_event.set(None)

            if self.wsgi_should_stop:
                self.async_event.set_nowait()
                break

            if asgi_task.done():
                break

        # HTTP response ends, wait for run_asgi's background tasks
        self.asgi_done.wait(self.wait_time)
        asgi_task.cancel()
        yield b""

    def error_response(
        self, start_response: StartResponse, exception: ExcInfo
    ) -> Iterable[bytes]:
        start_response(
            "500 Internal Server Error",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", "28"),
            ],
            exception,
        )
        yield b"Server got itself in trouble"
