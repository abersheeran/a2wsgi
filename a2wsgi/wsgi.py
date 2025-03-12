import asyncio
import contextvars
import functools
import sys
from concurrent.futures import ThreadPoolExecutor

from .asgi_typing import HTTPScope, Scope, Receive, Send, SendEvent
from .wsgi_typing import Environ, StartResponse, ExceptionInfo, WSGIApp, WriteCallable


class Body:
    def __init__(self, loop: asyncio.AbstractEventLoop, receive: Receive):
        self.buffer = bytearray()
        self.loop = loop
        self.receive = receive
        self._has_more = True

    @property
    def has_more(self):
        return self._has_more or bool(self.buffer)

    def _receive_more_data(self):
        if not self._has_more:
            return b""
        message = asyncio.run_coroutine_threadsafe(self.receive(), self.loop).result()
        self._has_more = message.get("more_body", False)
        return message.get("body", b"")

    def read(self, size: int = -1):
        while size == -1 or size > len(self.buffer):
            self.buffer.extend(self._receive_more_data())
            if not self._has_more:
                break
        if size == -1:
            result = bytes(self.buffer)
            self.buffer.clear()
        else:
            result = bytes(self.buffer[:size])
            del self.buffer[:size]
        return result

    def readline(self, limit: int = -1):
        while True:
            i = self.buffer.find(b"\n", 0, limit if limit > -1 else None)
            if i != -1:
                result = bytes(self.buffer[: i + 1])
                del self.buffer[: i + 1]
                return result
            if limit != -1:
                result = bytes(self.buffer[:limit])
                del self.buffer[:limit]
                return result
            if not self._has_more:
                break
            self.buffer.extend(self._receive_more_data())
        result = bytes(self.buffer)
        self.buffer.clear()
        return result

    def readlines(self, hint: int = -1):
        if not self.has_more:
            return []
        if hint == -1:
            raw = self.read()
            lines = raw.split(b"\n")
            if raw.endswith(b"\n"):
                lines.pop()
            return [line + b"\n" for line in lines]
        return [self.readline() for _ in range(hint)]

    def __iter__(self):
        while self.has_more:
            yield self.readline()


def unicode_to_wsgi(value: str):
    return value.encode(sys.getfilesystemencoding(), "surrogateescape").decode("iso-8859-1")


def build_environ(scope: HTTPScope, body: Body) -> Environ:
    script_name = scope.get("root_path", "").encode().decode("latin1")
    path_info = scope["path"].encode().decode("latin1")
    if path_info.startswith(script_name):
        path_info = path_info[len(script_name):]

    script_name_env = sys.environ.get("SCRIPT_NAME", "")
    if script_name_env:
        script_name = unicode_to_wsgi(script_name_env)

    environ: Environ = {
        "asgi.scope": scope,
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

    server = scope.get("server") or ("localhost", 80)
    environ["SERVER_NAME"], environ["SERVER_PORT"] = server[0], str(server[1])

    if scope.get("client"):
        environ["REMOTE_ADDR"], environ["REMOTE_PORT"] = scope["client"][0], str(scope["client"][1])

    for name, value in scope.get("headers", []):
        name = name.decode("latin1")
        value = value.decode("latin1")
        key = {
            "content-length": "CONTENT_LENGTH",
            "content-type": "CONTENT_TYPE"
        }.get(name, f"HTTP_{name.upper().replace('-', '_')}")
        if key in environ:
            value = environ[key] + "," + value
        environ[key] = value

    return environ


class WSGIMiddleware:
    def __init__(self, app: WSGIApp, workers: int = 10, send_queue_size: int = 10):
        self.app = app
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="WSGI")
        self.send_queue_size = send_queue_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            responder = WSGIResponder(self.app, self.executor, self.send_queue_size)
            return await responder(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1000})
        elif scope["type"] == "lifespan":
            await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.complete"})


class WSGIResponder:
    def __init__(self, app: WSGIApp, executor: ThreadPoolExecutor, send_queue_size: int):
        self.app = app
        self.executor = executor
        self.loop = asyncio.get_event_loop()
        self.send_queue = asyncio.Queue(send_queue_size)
        self.response_started = False
        self.exc_info = None

    async def __call__(self, scope: HTTPScope, receive: Receive, send: Send):
        body = Body(self.loop, receive)
        environ = build_environ(scope, body)
        sender_task = None
        try:
            sender_task = self.loop.create_task(self._sender(send))
            func = functools.partial(contextvars.copy_context().run, self._wsgi)
            await self.loop.run_in_executor(self.executor, func, environ, self.start_response)
            await self.send_queue.put(None)
            await sender_task
            if self.exc_info:
                raise self.exc_info[0].with_traceback(self.exc_info[1], self.exc_info[2])
        finally:
            if sender_task and not sender_task.done():
                sender_task.cancel()

    def send(self, message: SendEvent | None):
        asyncio.run_coroutine_threadsafe(self.send_queue.put(message), self.loop).result()

    async def _sender(self, send: Send):
        while True:
            message = await self.send_queue.get()
            if message is None:
                break
            await send(message)
            self.send_queue.task_done()

    def start_response(
        self,
        status: str,
        response_headers: list[tuple[str, str]],
        exc_info: ExceptionInfo | None = None,
    ) -> WriteCallable:
        self.exc_info = exc_info
        if not self.response_started:
            self.response_started = True
            code = int(status.split()[0])
            headers = [(k.strip().encode("latin1").lower(), v.strip().encode("latin1"))
                       for k, v in response_headers]
            self.send({"type": "http.response.start", "status": code, "headers": headers})
        return lambda chunk: self.send({"type": "http.response.body", "body": chunk, "more_body": True})

    def _wsgi(self, environ: Environ, start_response: StartResponse):
        iterable = self.app(environ, start_response)
        try:
            for chunk in iterable:
                self.send({"type": "http.response.body", "body": chunk, "more_body": True})
            self.send({"type": "http.response.body", "body": b""})
        finally:
            getattr(iterable, "close", lambda: None)()
