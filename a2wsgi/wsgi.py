import asyncio
import contextvars
import functools
import os
import sys
import typing
from concurrent.futures import ThreadPoolExecutor

from .asgi_typing import HTTPScope, Scope, Receive, Send, SendEvent
from .wsgi_typing import Environ, StartResponse, ExceptionInfo, WSGIApp, WriteCallable


class Body:
    def __init__(self, loop: asyncio.AbstractEventLoop, receive: Receive) -> None:
        self.buffer = bytearray()
        self.loop = loop
        self.receive = receive
        self._has_more = True

    @property
    def has_more(self) -> bool:
        return self._has_more or bool(self.buffer)

    def _receive_more_data(self) -> bytes:
        if not self._has_more:
            return b""
        message = asyncio.run_coroutine_threadsafe(self.receive(), loop=self.loop).result()
        self._has_more = message.get("more_body", False)
        return message.get("body", b"")

    def read(self, size: int = -1) -> bytes:
        while size == -1 or size > len(self.buffer):
            data = self._receive_more_data()
            if not data and not self._has_more:
                break
            self.buffer.extend(data)
            
        if size == -1:
            result = bytes(self.buffer)
            self.buffer.clear()
        else:
            result = bytes(self.buffer[:size])
            del self.buffer[:size]
        return result

    def readline(self, limit: int = -1) -> bytes:
        while True:
            lf_index = self.buffer.find(b"\n", 0, limit if limit > -1 else None)
            if lf_index != -1:
                result = bytes(self.buffer[: lf_index + 1])
                del self.buffer[: lf_index + 1]
                return result
            if limit != -1 and len(self.buffer) >= limit:
                result = bytes(self.buffer[:limit])
                del self.buffer[:limit]
                return result
            if not self._has_more:
                break
            self.buffer.extend(self._receive_more_data())

        result = bytes(self.buffer)
        self.buffer.clear()
        return result

    def readlines(self, hint: int = -1) -> typing.List[bytes]:
        if not self.has_more:
            return []
        if hint == -1:
            raw_data = self.read()
            return [line + b"\n" for line in raw_data.split(b"\n") if line or raw_data.endswith(b"\n")]
        return [self.readline() for _ in range(hint)]

    def __iter__(self) -> typing.Generator[bytes, None, None]:
        while self.has_more:
            yield self.readline()


def build_environ(scope: HTTPScope, body: Body) -> Environ:
    script_name = scope.get("root_path", "").encode("utf8").decode("latin1")
    path_info = scope["path"].encode("utf8").decode("latin1")
    if path_info.startswith(script_name):
        path_info = path_info[len(script_name):]

    script_name_env = os.environ.get("SCRIPT_NAME", "")
    if script_name_env:
        script_name = script_name_env.encode(sys.getfilesystemencoding(), "surrogateescape").decode("iso-8859-1")

    environ: Environ = {
        "asgi.scope": scope,  # type: ignore a2wsgi
        "REQUEST_METHOD": scope["method"],
        "SCRIPT_NAME": script_name,
        "PATH_INFO": path_info,
        "QUERY_STRING": scope["query_string"].decode("ascii"),
        "SERVER_PROTOCOL": f"HTTP/{scope['http_version']}",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": scope.get("scheme", "http"),
        "wsgi.input": body,
        "wsgi.errors": sys.stdout,
        "wsgi.multithread": True,
        "wsgi.multiprocess": True,
        "wsgi.run_once": False,
    }

    # Add server info
    server = scope.get("server", ("localhost", 80))
    environ["SERVER_NAME"], environ["SERVER_PORT"] = server[0], str(server[1] or 0)

    # Add client info if available
    client = scope.get("client")
    if client:
        environ["REMOTE_ADDR"], environ["REMOTE_PORT"] = client[0], str(client[1])

    # Process headers
    for name, value in scope.get("headers", []):
        name = name.decode("latin1")
        value = value.decode("latin1")
        
        if name == "content-length":
            key = "CONTENT_LENGTH"
        elif name == "content-type":
            key = "CONTENT_TYPE"
        else:
            key = f"HTTP_{name.upper().replace('-', '_')}"
            
        if key in environ:
            value = f"{environ[key]},{value}"
        
        environ[key] = value

    return environ


class WSGIMiddleware:
    def __init__(self, app: WSGIApp, workers: int = 10, send_queue_size: int = 10) -> None:
        self.app = app
        self.send_queue_size = send_queue_size
        self.executor = ThreadPoolExecutor(thread_name_prefix="WSGI", max_workers=workers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await WSGIResponder(self.app, self.executor, self.send_queue_size)(scope, receive, send)
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1000})
        elif scope["type"] == "lifespan":
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.complete"})


class WSGIResponder:
    def __init__(self, app: WSGIApp, executor: ThreadPoolExecutor, send_queue_size: int) -> None:
        self.app = app
        self.executor = executor
        self.loop = asyncio.get_event_loop()
        self.send_queue = asyncio.Queue(send_queue_size)
        self.response_started = False
        self.exc_info: typing.Any = None

    async def __call__(self, scope: HTTPScope, receive: Receive, send: Send) -> None:
        body = Body(self.loop, receive)
        environ = build_environ(scope, body)
        sender = self.loop.create_task(self._sender(send))
        
        try:
            context = contextvars.copy_context()
            await self.loop.run_in_executor(
                self.executor, 
                functools.partial(context.run, self._run_wsgi), 
                environ
            )
            await self.send_queue.put(None)
            await sender
            
            if self.exc_info:
                raise self.exc_info[0].with_traceback(self.exc_info[1], self.exc_info[2])
        finally:
            if not sender.done():
                sender.cancel()

    async def _sender(self, send: Send) -> None:
        while True:
            message = await self.send_queue.get()
            if message is None:
                break
            await send(message)
            self.send_queue.task_done()

    def _queue_message(self, message: typing.Optional[SendEvent]) -> None:
        asyncio.run_coroutine_threadsafe(
            self.send_queue.put(message), loop=self.loop
        ).result()

    def start_response(
        self,
        status: str,
        response_headers: typing.List[typing.Tuple[str, str]],
        exc_info: typing.Optional[ExceptionInfo] = None,
    ) -> WriteCallable:
        self.exc_info = exc_info
        
        if not self.response_started:
            self.response_started = True
            status_code = int(status.split(" ", 1)[0])
            headers = [
                (name.strip().encode("latin1").lower(), value.strip().encode("latin1"))
                for name, value in response_headers
            ]
            self._queue_message({"type": "http.response.start", "status": status_code, "headers": headers})
            
        return lambda chunk: self._queue_message(
            {"type": "http.response.body", "body": chunk, "more_body": True}
        )

    def _run_wsgi(self, environ: Environ) -> None:
        iterable = self.app(environ, self.start_response)
        try:
            for chunk in iterable:
                self._queue_message({"type": "http.response.body", "body": chunk, "more_body": True})
            self._queue_message({"type": "http.response.body", "body": b""})
        finally:
            if hasattr(iterable, "close"):
                iterable.close()