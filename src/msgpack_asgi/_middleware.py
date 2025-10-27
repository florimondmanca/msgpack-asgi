import io
import json
from functools import partial
from typing import Any, Callable, Type, cast

import msgpack
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from typing_extensions import Protocol

_msgpack_unpackb = partial(msgpack.unpackb, raw=False)


def _std_json_loads(data: bytes) -> Any:
    return json.loads(data)


def _std_json_dumps(obj: Any) -> bytes:
    return json.dumps(obj).encode()


class _StreamingUnpacker(Protocol):
    def __init__(
        self, *, unpackb: Callable[[bytes], Any], dumps: Callable[[Any], bytes]
    ) -> None: ...
    def feed(self, data: bytes) -> None: ...
    def decode(self) -> Any: ...
    def pack(self) -> bytes: ...


class _StreamingPacker(Protocol):
    def __init__(
        self, *, packb: Callable[[Any], bytes], loads: Callable[[bytes], Any]
    ) -> None: ...
    def feed(self, obj: Any) -> None: ...
    def decode(self) -> Any: ...
    def pack(self) -> bytes: ...


class StreamingJsonPacker:
    def __init__(
        self, *, packb: Callable[[Any], bytes], loads: Callable[[bytes], Any]
    ) -> None:
        self._packb = packb
        self._loads = loads
        self._buf = io.BytesIO()

    def feed(self, data: bytes) -> None:
        self._buf.write(data)

    def decode(self) -> Any:
        self._buf.seek(0)
        data = self._buf.getvalue()
        self._buf = io.BytesIO()
        return self._loads(data)

    def pack(self) -> bytes:
        return self._packb(self.decode())


class StreamingJsonUnpacker:
    def __init__(
        self, *, unpackb: Callable[[bytes], Any], dumps: Callable[[Any], bytes]
    ) -> None:
        self._unpackb = unpackb
        self._dumps = dumps
        self._buf = io.BytesIO()

    def feed(self, data: bytes) -> None:
        self._buf.write(data)

    def decode(self) -> Any:
        self._buf.seek(0)
        data = self._buf.getvalue()
        self._buf = io.BytesIO()
        return self._unpackb(data)

    def pack(self) -> bytes:
        return self._dumps(self.decode())


class MessagePackMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        packb: Callable[[Any], bytes] = cast(Callable, msgpack.packb),
        unpackb: Callable[[bytes], Any] = _msgpack_unpackb,
        # Default to official msgpack content type one:
        # https://www.iana.org/assignments/media-types/application/vnd.msgpack
        # Allow customization to support older implementations, such as those using
        # application/x-msgpack.
        content_type: str = "application/vnd.msgpack",
        unpacker_cls: Type[_StreamingUnpacker] = StreamingJsonUnpacker,
        packer_cls: Type[_StreamingPacker] = StreamingJsonPacker,
        loads: Callable[[bytes], Any] = _std_json_loads,
        dumps: Callable[[Any], bytes] = _std_json_dumps,
    ) -> None:
        self._app = app
        self._packb = packb
        self._unpackb = unpackb
        self._loads = loads
        self._dumps = dumps
        self._packer_cls = packer_cls
        self._unpacker_cls = unpacker_cls
        self._content_type = content_type

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            responder = _MessagePackResponder(
                self._app,
                packb=self._packb,
                unpackb=self._unpackb,
                loads=self._loads,
                dumps=self._dumps,
                packer_cls=self._packer_cls,
                unpacker_cls=self._unpacker_cls,
                content_type=self._content_type,
            )
            await responder(scope, receive, send)
            return
        await self._app(scope, receive, send)


class _MessagePackResponder:
    def __init__(
        self,
        app: ASGIApp,
        *,
        packb: Callable[[Any], bytes],
        unpackb: Callable[[bytes], Any],
        loads: Callable[[bytes], Any],
        dumps: Callable[[Any], bytes],
        packer_cls: Type[_StreamingPacker],
        unpacker_cls: Type[_StreamingUnpacker],
        content_type: str,
    ) -> None:
        self._app = app
        self._packer = packer_cls(packb=packb, loads=loads)
        self._unpacker = unpacker_cls(unpackb=unpackb, dumps=dumps)
        self._content_type = content_type
        self._should_decode_from_msgpack_to_json = False
        self._should_encode_from_json_to_msgpack = False
        self._receive: Receive = unattached_receive
        self._send: Send = unattached_send
        self._initial_message: Message = {}
        self._started = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = MutableHeaders(scope=scope)
        self._should_decode_from_msgpack_to_json = self._content_type in headers.get(
            "content-type", ""
        )
        # Take an initial guess, although we eventually may not
        # be able to do the conversion.
        self._should_encode_from_json_to_msgpack = (
            self._content_type in headers.getlist("accept")
        )
        self._receive = receive
        self._send = send

        if self._should_decode_from_msgpack_to_json:
            # We're going to present JSON content to the application,
            # so rewrite `Content-Type` for consistency and compliance
            # with possible downstream security checks in some frameworks.
            # See: https://github.com/florimondmanca/msgpack-asgi/issues/23
            headers["content-type"] = "application/json"

        await self._app(scope, self.receive_with_msgpack, self.send_with_msgpack)

    async def receive_with_msgpack(self) -> Message:
        message = await self._receive()

        if not self._should_decode_from_msgpack_to_json:
            return message
        if message["type"] != "http.request":
            return message

        body = message["body"]
        self._unpacker.feed(body)
        message["body"] = b""
        more_body = message.get("more_body", False)
        if more_body:
            return message

        message["body"] = self._unpacker.pack()
        return message

    async def send_with_msgpack(self, message: Message) -> None:
        if not self._should_encode_from_json_to_msgpack:
            await self._send(message)
            return

        if message["type"] == "http.response.start":
            headers = Headers(raw=message["headers"])
            if headers["content-type"] != "application/json":
                # Client accepts msgpack, but the app did not send JSON data.
                # (Note that it may have sent msgpack-encoded data.)
                self._should_encode_from_json_to_msgpack = False
                await self._send(message)
                return

            # Don't send the initial message until we've determined how to
            # modify the outgoing headers correctly.
            self.initial_message = message

        elif message["type"] == "http.response.body":
            assert self._should_encode_from_json_to_msgpack

            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            self._packer.feed(body)

            if more_body:
                return

            body = self._packer.pack()

            headers = MutableHeaders(raw=self.initial_message["headers"])
            headers["Content-Type"] = self._content_type
            headers["Content-Length"] = str(len(body))
            message["body"] = body

            await self._send(self.initial_message)
            await self._send(message)


async def unattached_receive() -> Message:
    raise RuntimeError("receive awaitable not set")  # pragma: no cover


async def unattached_send(message: Message) -> None:
    raise RuntimeError("send awaitable not set")  # pragma: no cover
