import httpx
import msgpack
import pytest

from msgpack_asgi.middleware import MessagePackMiddleware
from msgpack_asgi.responses import MsgPackResponse
from tests.utils import (
    mock_receive,
    mock_send,
)
from starlette.types import Scope, Receive, Send
from starlette.requests import Request
from starlette.responses import PlainTextResponse, JSONResponse


def test_msgpack_request() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive)
        content_type = request.headers["content-type"]
        data = await request.json()
        message = data["message"]
        text = f"content_type={content_type!r} message={message!r}"

        response = PlainTextResponse(text)
        await response(scope, receive, send)

    app = MessagePackMiddleware(app)

    with httpx.Client(app=app, base_url="http://testserver") as client:
        content = {"message": "Hello, world!"}
        body = msgpack.packb(content)
        r = client.post(
            "/", data=body, headers={"content-type": "application/x-msgpack"}
        )
        assert r.status_code == 200
        assert r.text == "content_type='application/x-msgpack' message='Hello, world!'"


def test_non_msgpack_request() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive)
        content_type = request.headers["content-type"]
        data = await request.json()
        message = data["message"]
        text = f"content_type={content_type!r} message={message!r}"

        response = PlainTextResponse(text)
        await response(scope, receive, send)

    app = MessagePackMiddleware(app)

    with httpx.Client(app=app, base_url="http://testserver") as client:
        r = client.post("/", json={"message": "Hello, world!"})
        assert r.status_code == 200
        assert r.text == "content_type='application/json' message='Hello, world!'"


def test_msgpack_accepted() -> None:
    app = MessagePackMiddleware(JSONResponse({"message": "Hello, world!"}))

    with httpx.Client(app=app, base_url="http://testserver") as client:
        r = client.get("/", headers={"accept": "application/x-msgpack"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/x-msgpack"
        expected_data = {"message": "Hello, world!"}
        assert int(r.headers["content-length"]) == len(msgpack.packb(expected_data))
        assert msgpack.unpackb(r.content, raw=False) == expected_data


def test_msgpack_accepted_but_response_is_not_json() -> None:
    app = MessagePackMiddleware(PlainTextResponse("Hello, world!"))

    with httpx.Client(app=app, base_url="http://testserver") as client:
        r = client.get("/", headers={"accept": "application/x-msgpack"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "text/plain; charset=utf-8"
        assert r.text == "Hello, world!"


def test_msgpack_accepted_and_response_is_already_msgpack() -> None:
    app = MessagePackMiddleware(MsgPackResponse({"message": "Hello, world!"}))

    with httpx.Client(app=app, base_url="http://testserver") as client:
        r = client.get("/", headers={"accept": "application/x-msgpack"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/x-msgpack"
        expected_data = {"message": "Hello, world!"}
        assert int(r.headers["content-length"]) == len(msgpack.packb(expected_data))
        assert msgpack.unpackb(r.content, raw=False) == expected_data


def test_msgpack_not_accepted() -> None:
    app = MessagePackMiddleware(JSONResponse({"message": "Hello, world!"}))

    with httpx.Client(app=app, base_url="http://testserver") as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/json"
        assert r.json() == {"message": "Hello, world!"}
        with pytest.raises(ValueError):
            msgpack.unpackb(r.content)


@pytest.mark.asyncio
async def test_request_is_not_http() -> None:
    async def lifespan_only_app(scope: Scope, receive: Receive, send: Send) -> None:
        assert scope["type"] == "lifespan"

    app = MessagePackMiddleware(lifespan_only_app)
    scope = {"type": "lifespan"}
    await app(scope, mock_receive, mock_send)
