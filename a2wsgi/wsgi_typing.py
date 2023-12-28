"""
https://peps.python.org/pep-3333/
"""
from types import TracebackType
from typing import (
    Any,
    Callable,
    Iterable,
    List,
    Optional,
    Protocol,
    Tuple,
    Type,
    TypedDict,
)

CGIRequiredDefined = TypedDict(
    "CGIRequiredDefined",
    {
        # The HTTP request method, such as GET or POST. This cannot ever be an
        # empty string, and so is always required.
        "REQUEST_METHOD": str,
        # When HTTP_HOST is not set, these variables can be combined to determine
        # a default.
        # SERVER_NAME and SERVER_PORT are required strings and must never be empty.
        "SERVER_NAME": str,
        "SERVER_PORT": str,
        # The version of the protocol the client used to send the request.
        # Typically this will be something like "HTTP/1.0" or "HTTP/1.1" and
        # may be used by the application to determine how to treat any HTTP
        # request headers. (This variable should probably be called REQUEST_PROTOCOL,
        # since it denotes the protocol used in the request, and is not necessarily
        # the protocol that will be used in the server's response. However, for
        # compatibility with CGI we have to keep the existing name.)
        "SERVER_PROTOCOL": str,
    },
)

CGIOptionalDefined = TypedDict(
    "CGIOptionalDefined",
    {
        "REQUEST_URI": str,
        "REMOTE_ADDR": str,
        "REMOTE_PORT": str,
        # The initial portion of the request URL’s “path” that corresponds to the
        # application object, so that the application knows its virtual “location”.
        # This may be an empty string, if the application corresponds to the “root”
        # of the server.
        "SCRIPT_NAME": str,
        # The remainder of the request URL’s “path”, designating the virtual
        # “location” of the request’s target within the application. This may be an
        # empty string, if the request URL targets the application root and does
        # not have a trailing slash.
        "PATH_INFO": str,
        # The portion of the request URL that follows the “?”, if any. May be empty
        # or absent.
        "QUERY_STRING": str,
        # The contents of any Content-Type fields in the HTTP request. May be empty
        # or absent.
        "CONTENT_TYPE": str,
        # The contents of any Content-Length fields in the HTTP request. May be empty
        # or absent.
        "CONTENT_LENGTH": str,
    },
    total=False,
)


class InputStream(Protocol):
    """
    An input stream (file-like object) from which the HTTP request body bytes can be
    read. (The server or gateway may perform reads on-demand as requested by the
    application, or it may pre- read the client's request body and buffer it in-memory
    or on disk, or use any other technique for providing such an input stream, according
    to its preference.)
    """

    def read(self, size: int = -1, /) -> bytes:
        """
        The server is not required to read past the client's specified Content-Length,
        and should simulate an end-of-file condition if the application attempts to read
        past that point. The application should not attempt to read more data than is
        specified by the CONTENT_LENGTH variable.
        A server should allow read() to be called without an argument, and return the
        remainder of the client's input stream.
        A server should return empty bytestrings from any attempt to read from an empty
        or exhausted input stream.
        """
        raise NotImplementedError

    def readline(self, limit: int = -1, /) -> bytes:
        """
        Servers should support the optional "size" argument to readline(), but as in
        WSGI 1.0, they are allowed to omit support for it.
        (In WSGI 1.0, the size argument was not supported, on the grounds that it might
        have been complex to implement, and was not often used in practice... but then
        the cgi module started using it, and so practical servers had to start
        supporting it anyway!)
        """
        raise NotImplementedError

    def readlines(self, hint: int = -1, /) -> List[bytes]:
        """
        Note that the hint argument to readlines() is optional for both caller and
        implementer. The application is free not to supply it, and the server or gateway
        is free to ignore it.
        """
        raise NotImplementedError


class ErrorStream(Protocol):
    """
    An output stream (file-like object) to which error output can be written,
    for the purpose of recording program or other errors in a standardized and
    possibly centralized location. This should be a "text mode" stream;
    i.e., applications should use "\n" as a line ending, and assume that it will
    be converted to the correct line ending by the server/gateway.
    (On platforms where the str type is unicode, the error stream should accept
    and log arbitrary unicode without raising an error; it is allowed, however,
    to substitute characters that cannot be rendered in the stream's encoding.)
    For many servers, wsgi.errors will be the server's main error log. Alternatively,
    this may be sys.stderr, or a log file of some sort. The server's documentation
    should include an explanation of how to configure this or where to find the
    recorded output. A server or gateway may supply different error streams to
    different applications, if this is desired.
    """

    def flush(self) -> None:
        """
        Since the errors stream may not be rewound, servers and gateways are free to
        forward write operations immediately, without buffering. In this case, the
        flush() method may be a no-op. Portable applications, however, cannot assume
        that output is unbuffered or that flush() is a no-op. They must call flush()
        if they need to ensure that output has in fact been written.
        (For example, to minimize intermingling of data from multiple processes writing
        to the same error log.)
        """
        raise NotImplementedError

    def write(self, s: str, /) -> Any:
        raise NotImplementedError

    def writelines(self, seq: List[str], /) -> Any:
        raise NotImplementedError


WSGIDefined = TypedDict(
    "WSGIDefined",
    {
        "wsgi.version": Tuple[int, int],  # e.g. (1, 0)
        "wsgi.url_scheme": str,  # e.g. "http" or "https"
        "wsgi.input": InputStream,
        "wsgi.errors": ErrorStream,
        # This value should evaluate true if the application object may be simultaneously
        # invoked by another thread in the same process, and should evaluate false otherwise.
        "wsgi.multithread": bool,
        # This value should evaluate true if an equivalent application object may be
        # simultaneously invoked by another process, and should evaluate false otherwise.
        "wsgi.multiprocess": bool,
        # This value should evaluate true if the server or gateway expects (but does
        # not guarantee!) that the application will only be invoked this one time during
        # the life of its containing process. Normally, this will only be true for a
        # gateway based on CGI (or something similar).
        "wsgi.run_once": bool,
    },
)


class Environ(CGIRequiredDefined, CGIOptionalDefined, WSGIDefined):
    """
    WSGI Environ
    """


ExceptionInfo = Tuple[Type[BaseException], BaseException, Optional[TracebackType]]

# https://peps.python.org/pep-3333/#the-write-callable
WriteCallable = Callable[[bytes], None]


class StartResponse(Protocol):
    def __call__(
        self,
        status: str,
        response_headers: List[Tuple[str, str]],
        exc_info: Optional[ExceptionInfo] = None,
        /,
    ) -> WriteCallable:
        raise NotImplementedError


IterableChunks = Iterable[bytes]

WSGIApp = Callable[[Environ, StartResponse], IterableChunks]
