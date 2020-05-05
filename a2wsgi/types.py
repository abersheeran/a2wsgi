from typing import (
    Any,
    MutableMapping,
    Callable,
    Iterable,
    Tuple,
    AnyStr,
    Awaitable,
)

Message = MutableMapping[str, Any]

Scope = MutableMapping[str, Any]

Receive = Callable[[], Awaitable[Message]]

Send = Callable[[Message], Awaitable[None]]

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

Environ = MutableMapping[str, Any]

StartResponse = Callable[[str, Iterable[Tuple[str, str]]], None]

WSGIApp = Callable[[Environ, StartResponse], Iterable[AnyStr]]
