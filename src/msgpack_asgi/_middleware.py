import json

import msgpack
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class MessagePackMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            responder = _MessagePackResponder(self.app)
            await responder(scope, receive, send)
            return
        await self.app(scope, receive, send)


class _MessagePackResponder:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.should_decode_from_msgpack_to_json = False
        self.should_encode_from_json_to_msgpack = False
        self.receive: Receive = unattached_receive
        self.send: Send = unattached_send
        self.initial_message: Message = {}
        self.started = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = Headers(scope=scope)
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

        obj = msgpack.unpackb(body, raw=False)
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

            body = msgpack.packb(json.loads(body))

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
