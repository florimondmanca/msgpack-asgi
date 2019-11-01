import msgpack
from starlette.types import Scope, Receive, Send


async def msgpack_app(scope: Scope, receive: Receive, send: Send) -> None:
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/x-msgpack"]],
        }
    )
    body = msgpack.packb({"message": "Hello, world!"})
    await send({"type": "http.response.body", "body": body})
