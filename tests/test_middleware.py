import httpx
import msgpack
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import Receive, Scope, Send

from msgpack_asgi.middleware import MessagePackMiddleware
from msgpack_asgi.responses import MessagePackResponse
from tests.utils import mock_receive, mock_send


@pytest.mark.asyncio
async def test_msgpack_request() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive)
        content_type = request.headers["content-type"]
        data = await request.json()
        message = data["message"]
        text = f"content_type={content_type!r} message={message!r}"

        response = PlainTextResponse(text)
        await response(scope, receive, send)

    app = MessagePackMiddleware(app)

    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        content = {"message": "Hello, world!"}
        body = msgpack.packb(content)
        r = await client.post(
            "/", data=body, headers={"content-type": "application/x-msgpack"}
        )
        assert r.status_code == 200
        assert r.text == "content_type='application/x-msgpack' message='Hello, world!'"


@pytest.mark.asyncio
async def test_non_msgpack_request() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive)
        content_type = request.headers["content-type"]
        data = await request.json()
        message = data["message"]
        text = f"content_type={content_type!r} message={message!r}"

        response = PlainTextResponse(text)
        await response(scope, receive, send)

    app = MessagePackMiddleware(app)

    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        r = await client.post("/", json={"message": "Hello, world!"})
        assert r.status_code == 200
        assert r.text == "content_type='application/json' message='Hello, world!'"


@pytest.mark.asyncio
async def test_msgpack_accepted() -> None:
    app = MessagePackMiddleware(JSONResponse({"message": "Hello, world!"}))

    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        r = await client.get("/", headers={"accept": "application/x-msgpack"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/x-msgpack"
        expected_data = {"message": "Hello, world!"}
        assert int(r.headers["content-length"]) == len(msgpack.packb(expected_data))
        assert msgpack.unpackb(r.content, raw=False) == expected_data


@pytest.mark.asyncio
async def test_msgpack_accepted_but_response_is_not_json() -> None:
    app = MessagePackMiddleware(PlainTextResponse("Hello, world!"))

    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        r = await client.get("/", headers={"accept": "application/x-msgpack"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "text/plain; charset=utf-8"
        assert r.text == "Hello, world!"


@pytest.mark.asyncio
async def test_msgpack_accepted_and_response_is_already_msgpack() -> None:
    app = MessagePackMiddleware(MessagePackResponse({"message": "Hello, world!"}))

    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        r = await client.get("/", headers={"accept": "application/x-msgpack"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/x-msgpack"
        expected_data = {"message": "Hello, world!"}
        assert int(r.headers["content-length"]) == len(msgpack.packb(expected_data))
        assert msgpack.unpackb(r.content, raw=False) == expected_data


@pytest.mark.asyncio
async def test_msgpack_not_accepted() -> None:
    app = MessagePackMiddleware(JSONResponse({"message": "Hello, world!"}))

    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        r = await client.get("/")
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
