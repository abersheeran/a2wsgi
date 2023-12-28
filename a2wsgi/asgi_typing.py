"""
https://asgi.readthedocs.io/en/latest/specs/index.html
"""
import sys
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    Literal,
    Optional,
    Tuple,
    TypedDict,
    Union,
)

if sys.version_info >= (3, 11):
    from typing import NotRequired
else:
    from typing_extensions import NotRequired


class ASGIVersions(TypedDict):
    spec_version: str
    version: Literal["3.0"]


class HTTPScope(TypedDict):
    type: Literal["http"]
    asgi: ASGIVersions
    http_version: str
    method: str
    scheme: str
    path: str
    raw_path: NotRequired[bytes]
    query_string: bytes
    root_path: str
    headers: Iterable[Tuple[bytes, bytes]]
    client: NotRequired[Tuple[str, int]]
    server: NotRequired[Tuple[str, Optional[int]]]
    state: NotRequired[Dict[str, Any]]
    extensions: NotRequired[Dict[str, Dict[object, object]]]


class WebSocketScope(TypedDict):
    type: Literal["websocket"]
    asgi: ASGIVersions
    http_version: str
    scheme: str
    path: str
    raw_path: bytes
    query_string: bytes
    root_path: str
    headers: Iterable[Tuple[bytes, bytes]]
    client: NotRequired[Tuple[str, int]]
    server: NotRequired[Tuple[str, Optional[int]]]
    subprotocols: Iterable[str]
    state: NotRequired[Dict[str, Any]]
    extensions: NotRequired[Dict[str, Dict[object, object]]]


class LifespanScope(TypedDict):
    type: Literal["lifespan"]
    asgi: ASGIVersions
    state: NotRequired[Dict[str, Any]]


WWWScope = Union[HTTPScope, WebSocketScope]
Scope = Union[HTTPScope, WebSocketScope, LifespanScope]


class HTTPRequestEvent(TypedDict):
    type: Literal["http.request"]
    body: bytes
    more_body: NotRequired[bool]


class HTTPResponseStartEvent(TypedDict):
    type: Literal["http.response.start"]
    status: int
    headers: NotRequired[Iterable[Tuple[bytes, bytes]]]
    trailers: NotRequired[bool]


class HTTPResponseBodyEvent(TypedDict):
    type: Literal["http.response.body"]
    body: NotRequired[bytes]
    more_body: NotRequired[bool]


class HTTPDisconnectEvent(TypedDict):
    type: Literal["http.disconnect"]


class WebSocketConnectEvent(TypedDict):
    type: Literal["websocket.connect"]


class WebSocketAcceptEvent(TypedDict):
    type: Literal["websocket.accept"]
    subprotocol: NotRequired[str]
    headers: NotRequired[Iterable[Tuple[bytes, bytes]]]


class WebSocketReceiveEvent(TypedDict):
    type: Literal["websocket.receive"]
    bytes: NotRequired[bytes]
    text: NotRequired[str]


class WebSocketSendEvent(TypedDict):
    type: Literal["websocket.send"]
    bytes: NotRequired[bytes]
    text: NotRequired[str]


class WebSocketDisconnectEvent(TypedDict):
    type: Literal["websocket.disconnect"]
    code: int


class WebSocketCloseEvent(TypedDict):
    type: Literal["websocket.close"]
    code: NotRequired[int]
    reason: NotRequired[str]


class LifespanStartupEvent(TypedDict):
    type: Literal["lifespan.startup"]


class LifespanShutdownEvent(TypedDict):
    type: Literal["lifespan.shutdown"]


class LifespanStartupCompleteEvent(TypedDict):
    type: Literal["lifespan.startup.complete"]


class LifespanStartupFailedEvent(TypedDict):
    type: Literal["lifespan.startup.failed"]
    message: str


class LifespanShutdownCompleteEvent(TypedDict):
    type: Literal["lifespan.shutdown.complete"]


class LifespanShutdownFailedEvent(TypedDict):
    type: Literal["lifespan.shutdown.failed"]
    message: str


ReceiveEvent = Union[
    HTTPRequestEvent,
    HTTPDisconnectEvent,
    WebSocketConnectEvent,
    WebSocketReceiveEvent,
    WebSocketDisconnectEvent,
    LifespanStartupEvent,
    LifespanShutdownEvent,
]

SendEvent = Union[
    HTTPResponseStartEvent,
    HTTPResponseBodyEvent,
    HTTPDisconnectEvent,
    WebSocketAcceptEvent,
    WebSocketSendEvent,
    WebSocketCloseEvent,
    LifespanStartupCompleteEvent,
    LifespanStartupFailedEvent,
    LifespanShutdownCompleteEvent,
    LifespanShutdownFailedEvent,
]

Receive = Callable[[], Awaitable[ReceiveEvent]]

Send = Callable[[SendEvent], Awaitable[None]]

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
