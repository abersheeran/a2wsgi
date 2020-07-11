from types import TracebackType
from typing import (
    Type,
    Any,
    MutableMapping,
    Callable,
    Iterable,
    Tuple,
    Awaitable,
    Optional,
)

ExcInfo = Tuple[Type[BaseException], BaseException, Optional[TracebackType]]

Message = MutableMapping[str, Any]

Scope = MutableMapping[str, Any]

Receive = Callable[[], Awaitable[Message]]

Send = Callable[[Message], Awaitable[None]]

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

Environ = MutableMapping[str, Any]

StartResponse = Callable[[str, Iterable[Tuple[str, str]], Optional[ExcInfo]], None]

WSGIApp = Callable[[Environ, StartResponse], Iterable[bytes]]
