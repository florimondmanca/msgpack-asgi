import io
import json
from functools import partial
from typing import Any, Callable, cast

import msgpack
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_msgpack_unpackb = partial(msgpack.unpackb, raw=False)


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
        self._packb = packb
        self._unpackb = unpackb
        self._content_type = content_type
        self._should_decode_from_msgpack_to_json = False
        self._should_encode_from_json_to_msgpack = False
        self._receive: Receive = unattached_receive
        self._send: Send = unattached_send
        self._initial_message: Message = {}
        self._started = False
        self._allow_naive_streaming = allow_naive_streaming
        self._response_buffer: io.BytesIO | None = None

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

        if message["type"] != "http.request":
            # Could be http.disconnect
            return message

        if not self._should_decode_from_msgpack_to_json:
            return message

        if self._allow_naive_streaming:
            body_buffer = io.BytesIO()

            while True:
                body_buffer.write(message["body"])

                if not message.get("more_body", False):
                    break

                message = await self._receive()

            message["body"] = json.dumps(self._unpackb(body_buffer.getvalue())).encode()

            return message

        body = message["body"]

        if message.get("more_body", False):
            # Some implementations (e.g. HTTPX) may send one more empty-body message.
            # Make sure they don't send one that contains a body, or it means
            # that clients attempt to stream the request body which has not
            # been explicitly allowed.
            message = await self._receive()

            if message["body"] != b"":
                raise NotImplementedError(
                    "Streaming msgpack request not supported. To allow naive (buffered)"
                    " streaming, set allow_naive_streaming=True in the middleware."
                )

        message["body"] = json.dumps(self._unpackb(body)).encode() if body else b"{}"

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
            body = message.get("body", b"")

            if self._allow_naive_streaming:
                if self._response_buffer is None:
                    self._response_buffer = io.BytesIO()

                self._response_buffer.write(body)

                if message.get("more_body", False):
                    return

                body = self._packb(json.loads(self._response_buffer.getvalue()))
            elif message.get("more_body", False):
                raise NotImplementedError(
                    "Streaming msgpack response not supported. To allow naive "
                    "(buffered) streaming, set allow_naive_streaming=True in the "
                    "middleware."
                )
            else:
                body = self._packb(json.loads(body))

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
