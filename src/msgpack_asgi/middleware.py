import msgpack
import json
import io

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class MsgPackMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def _get_app(self, scope: Scope) -> ASGIApp:
        if scope["type"] != "http":
            return self.app
        headers = Headers(scope=scope)
        if "application/x-msgpack" not in headers.getlist("Content-Type"):
            return self.app
        return MsgPackResponder(self.app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = self._get_app(scope)
        await app(scope, receive, send)


class MsgPackResponder:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.send: Send = unattached_send
        self.initial_message: Message = {}
        self.started = False
        self.buffer = io.BytesIO()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self.send_with_msgpack)

    async def send_with_msgpack(self, message: Message) -> None:
        message_type = message["type"]
        if message_type == "http.response.start":
            # Don't send the initial message until we've determined how to
            # modify the outgoing headers correctly.
            self.initial_message = message

        elif message_type == "http.response.body" and not self.started:
            self.started = True
            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            if not more_body:
                # Standard response.
                self.buffer.write(body)
                self.buffer.close()
                body = self.buffer.getvalue()
                obj = msgpack.unpackb(body)
                body = json.dumps(obj)

                headers = MutableHeaders(raw=self.initial_message["headers"])
                headers["Content-Type"] = "application/x-msgpack"
                headers["Content-Length"] = str(len(body))
                message["body"] = body

                await self.send(self.initial_message)
                await self.send(message)

            else:
                # Initial body in streaming response.
                headers = MutableHeaders(raw=self.initial_message["headers"])
                headers["Content-Type"] = "application/x-msgpack"
                del headers["Content-Length"]

                self.buffer.write(body)
                message["body"] = self.buffer.getvalue()
                self.buffer.seek(0)
                self.buffer.truncate()

                await self.send(self.initial_message)
                await self.send(message)

        elif message_type == "http.response.body":
            # Remaining body in streaming response.
            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            self.buffer.write(body)
            if not more_body:
                self.buffer.close()

            message["body"] = self.buffer.getvalue()
            self.buffer.seek(0)
            self.buffer.truncate()

            await self.send(message)


async def unattached_send(message: Message) -> None:
    raise RuntimeError("send awaitable not set")  # pragma: no cover
