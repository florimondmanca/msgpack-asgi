import io
import json
from functools import partial
from typing import Any, Callable, cast

import msgpack
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_NAIVE_STREAMING_ERROR = (
    "Streaming msgpack requests not supported. To allow naive (buffered)"
    " streaming, set allow_naive_streaming=True in the middleware."
)

_msgpack_unpackb = partial(msgpack.unpackb, raw=False)


def _std_json_dumps(*args: Any, **kwargs: Any) -> bytes:
    return json.dumps(*args, **kwargs).encode()


class _BufferedTranscoder:
    def __init__(
        self,
        *,
        encode: Callable[[Any], bytes],
        decode: Callable[[bytes], Any],
        allow_buffering: bool,
    ) -> None:
        self._encode = encode
        self._decode = decode
        self._buf = io.BytesIO()
        self._allow_buffering = allow_buffering

    def feed(self, data: bytes) -> None:
        more_data = len(data) > 0
        can_accept = self._allow_buffering or self._buf.tell() == 0
        if not can_accept and more_data:
            raise NotImplementedError(_NAIVE_STREAMING_ERROR)
        self._buf.write(data)

    def _decode_buffer(self) -> Any:
        data = self._buf.getvalue()
        self._buf = io.BytesIO()
        return self._decode(data)

    def transcode(self) -> bytes:
        return self._encode(self._decode_buffer())


class BufferedJsonPacker(_BufferedTranscoder):
    def __init__(self, *, packb: Callable[[Any], bytes], allow_buffering: bool) -> None:
        super().__init__(
            encode=packb, decode=json.loads, allow_buffering=allow_buffering
        )


class BufferedJsonUnpacker(_BufferedTranscoder):
    def __init__(self, unpackb: Callable[[bytes], Any], allow_buffering: bool) -> None:
        super().__init__(
            encode=_std_json_dumps, decode=unpackb, allow_buffering=allow_buffering
        )


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
        allow_naive_streaming: bool = False,
    ) -> None:
        self._app = app
        self._packb = packb
        self._unpackb = unpackb
        self._content_type = content_type
        self._allow_naive_streaming = allow_naive_streaming

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            responder = _MessagePackResponder(
                self._app,
                packb=self._packb,
                unpackb=self._unpackb,
                content_type=self._content_type,
                allow_naive_streaming=self._allow_naive_streaming,
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
        allow_naive_streaming: bool,
        content_type: str,
    ) -> None:
        self._app = app
        self._packer = BufferedJsonPacker(
            packb=packb, allow_buffering=allow_naive_streaming
        )
        self._unpacker = BufferedJsonUnpacker(
            unpackb=unpackb, allow_buffering=allow_naive_streaming
        )
        self._content_type = content_type
        self._should_decode_from_msgpack_to_json = False
        self._should_encode_from_json_to_msgpack = False
        self._receive: Receive = unattached_receive
        self._send: Send = unattached_send
        self._initial_message: Message = {}
        self._started = False
        self._allow_naive_streaming = allow_naive_streaming

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

        message["body"] = self._unpacker.transcode()
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

            body = self._packer.transcode()

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
