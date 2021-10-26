import json
from functools import partial
from typing import Any, Callable

import msgpack
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_msgpack_unpackb = partial(msgpack.unpackb, raw=False)


class MessagePackMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        packb: Callable[[Any], bytes] = msgpack.packb,
        unpackb: Callable[[bytes], Any] = _msgpack_unpackb,
    ) -> None:
        self.app = app
        self.packb = packb
        self.unpackb = unpackb

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            responder = _MessagePackResponder(
                self.app, packb=self.packb, unpackb=self.unpackb
            )
            await responder(scope, receive, send)
            return
        await self.app(scope, receive, send)


class _MessagePackResponder:
    def __init__(
        self,
        app: ASGIApp,
        *,
        packb: Callable[[Any], bytes],
        unpackb: Callable[[bytes], Any],
    ) -> None:
        self.app = app
        self.packb = packb
        self.unpackb = unpackb
        self.should_decode_from_msgpack_to_json = False
        self.should_encode_from_json_to_msgpack = False
        self.receive: Receive = unattached_receive
        self.send: Send = unattached_send
        self.initial_message: Message = {}
        self.started = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = MutableHeaders(scope=scope)
        self.should_decode_from_msgpack_to_json = (
            "application/x-msgpack" in headers.get("content-type", "")
        )
        # Take an initial guess, although we eventually may not
        # be able to do the conversion.
        self.should_encode_from_json_to_msgpack = (
            "application/x-msgpack" in headers.getlist("accept")
        )
        self.receive = receive
        self.send = send

        if self.should_decode_from_msgpack_to_json:
            # We're going to present JSON content to the application,
            # so rewrite `Content-Type` for consistency and compliance
            # with possible downstream security checks in some frameworks.
            # See: https://github.com/florimondmanca/msgpack-asgi/issues/23
            headers["content-type"] = "application/json"

        await self.app(scope, self.receive_with_msgpack, self.send_with_msgpack)

    async def receive_with_msgpack(self) -> Message:
        message = await self.receive()

        if not self.should_decode_from_msgpack_to_json:
            return message

        assert message["type"] == "http.request"

        body = message["body"]
        more_body = message.get("more_body", False)
        if more_body:
            # Some implementations (e.g. HTTPX) may send one more empty-body message.
            # Make sure they don't send one that contains a body, or it means
            # that clients attempt to stream the request body.
            message = await self.receive()
            if message["body"] != b"":  # pragma: no cover
                raise NotImplementedError(
                    "Streaming the request body isn't supported yet"
                )

        obj = self.unpackb(body)
        message["body"] = json.dumps(obj).encode()

        return message

    async def send_with_msgpack(self, message: Message) -> None:
        if not self.should_encode_from_json_to_msgpack:
            await self.send(message)
            return

        if message["type"] == "http.response.start":
            headers = Headers(raw=message["headers"])
            if headers["content-type"] != "application/json":
                # Client accepts msgpack, but the app did not send JSON data.
                # (Note that it may have sent msgpack-encoded data.)
                self.should_encode_from_json_to_msgpack = False
                await self.send(message)
                return

            # Don't send the initial message until we've determined how to
            # modify the ougoging headers correctly.
            self.initial_message = message

        elif message["type"] == "http.response.body":
            assert self.should_encode_from_json_to_msgpack

            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            if more_body:  # pragma: no cover
                raise NotImplementedError(
                    "Streaming the response body isn't supported yet"
                )

            body = self.packb(json.loads(body))

            headers = MutableHeaders(raw=self.initial_message["headers"])
            headers["Content-Type"] = "application/x-msgpack"
            headers["Content-Length"] = str(len(body))
            message["body"] = body

            await self.send(self.initial_message)
            await self.send(message)


async def unattached_receive() -> Message:
    raise RuntimeError("receive awaitable not set")  # pragma: no cover


async def unattached_send(message: Message) -> None:
    raise RuntimeError("send awaitable not set")  # pragma: no cover
