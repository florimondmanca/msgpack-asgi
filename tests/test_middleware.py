import json
from collections.abc import AsyncIterator

import httpx
import msgpack
import pytest
from starlette.requests import Request
from starlette.responses import (
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from msgpack_asgi import MessagePackMiddleware
from tests.utils import mock_receive, mock_send


def _make_client(app: ASGIApp) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    )


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

    async with _make_client(app) as client:
        content = {"message": "Hello, world!"}
        body = msgpack.packb(content)
        r = await client.post(
            "/", content=body, headers={"content-type": "application/vnd.msgpack"}
        )
        assert r.status_code == 200
        assert r.text == "content_type='application/json' message='Hello, world!'"


@pytest.mark.asyncio
async def test_non_msgpack_request() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive)
        content_type = request.headers["content-type"]
        message = (await request.body()).decode()
        text = f"content_type={content_type!r} message={message!r}"

        response = PlainTextResponse(text)
        await response(scope, receive, send)

    app = MessagePackMiddleware(app)

    async with _make_client(app) as client:
        r = await client.post(
            "/",
            content="Hello, world!",
            headers={"content-type": "text/plain"},
        )
        assert r.status_code == 200
        assert r.text == "content_type='text/plain' message='Hello, world!'"


@pytest.mark.asyncio
async def test_msgpack_accepted() -> None:
    app = MessagePackMiddleware(JSONResponse({"message": "Hello, world!"}))

    async with _make_client(app) as client:
        r = await client.get("/", headers={"accept": "application/vnd.msgpack"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/vnd.msgpack"
        expected_data = {"message": "Hello, world!"}
        assert int(r.headers["content-length"]) == len(msgpack.packb(expected_data))
        assert msgpack.unpackb(r.content, raw=False) == expected_data


@pytest.mark.asyncio
async def test_msgpack_accepted_but_response_is_not_json() -> None:
    app = MessagePackMiddleware(PlainTextResponse("Hello, world!"))

    async with _make_client(app) as client:
        r = await client.get("/", headers={"accept": "application/vnd.msgpack"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "text/plain; charset=utf-8"
        assert r.text == "Hello, world!"


@pytest.mark.asyncio
async def test_msgpack_accepted_and_response_is_already_msgpack() -> None:
    data = msgpack.packb({"message": "Hello, world!"})
    response = Response(data, media_type="application/vnd.msgpack")
    app = MessagePackMiddleware(response)

    async with _make_client(app) as client:
        r = await client.get("/", headers={"accept": "application/vnd.msgpack"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/vnd.msgpack"
        expected_data = {"message": "Hello, world!"}
        assert int(r.headers["content-length"]) == len(msgpack.packb(expected_data))
        assert msgpack.unpackb(r.content, raw=False) == expected_data


@pytest.mark.asyncio
async def test_msgpack_not_accepted() -> None:
    app = MessagePackMiddleware(JSONResponse({"message": "Hello, world!"}))

    async with _make_client(app) as client:
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


@pytest.mark.asyncio
async def test_packb_unpackb() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        assert await request.json() == {"message": "unpacked"}

        response = JSONResponse({"message": "Hello, World!"})
        await response(scope, receive, send)

    app = MessagePackMiddleware(
        app, packb=lambda _: b"packed", unpackb=lambda _: {"message": "unpacked"}
    )

    async with _make_client(app) as client:
        r = await client.post(
            "/",
            content="Hello, World",
            headers={
                "content-type": "application/vnd.msgpack",
                "accept": "application/vnd.msgpack",
            },
        )
        assert "packed" == r.text


@pytest.mark.asyncio
async def test_custom_content_type() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive)
        content_type = request.headers["content-type"]
        data = await request.json()
        message = data["message"]
        text = f"content_type={content_type!r} message={message!r}"

        response = JSONResponse({"text": text})
        await response(scope, receive, send)

    app = MessagePackMiddleware(app, content_type="application/x-msgpack")

    async with _make_client(app) as client:
        content = {"message": "Hello, world!"}
        body = msgpack.packb(content)
        r = await client.post(
            "/",
            content=body,
            headers={
                "content-type": "application/x-msgpack",
                "accept": "application/x-msgpack",
            },
        )
        assert r.headers["content-type"] == "application/x-msgpack"
        assert r.status_code == 200
        expected_data = {
            "text": "content_type='application/json' message='Hello, world!'"
        }
        assert int(r.headers["content-length"]) == len(msgpack.packb(expected_data))
        assert msgpack.unpackb(r.content, raw=False) == expected_data


@pytest.mark.asyncio
async def test_buffered_streaming() -> None:
    chunk_size = 8
    request_data = {"message": "unpacked"}
    request_content = msgpack.packb(request_data)
    response_data = {"message": "Hello, World!"}
    response_json = json.dumps(response_data).encode()

    async def response_content_gen() -> AsyncIterator[bytes]:
        for i in range(0, len(response_json), chunk_size):
            yield response_json[i : min(i + chunk_size, len(response_json))]

    async def request_content_gen() -> AsyncIterator[bytes]:
        for i in range(0, len(request_content), chunk_size):
            yield request_content[i : min(i + chunk_size, len(request_content))]

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        assert await request.json() == request_data

        response = StreamingResponse(
            content=response_content_gen(), media_type="application/json"
        )
        await response(scope, receive, send)

    app = MessagePackMiddleware(app, allow_naive_streaming=True)

    async with _make_client(app) as client:
        r = await client.post(
            "/",
            content=request_content_gen(),
            headers={
                "content-type": "application/vnd.msgpack",
                "accept": "application/vnd.msgpack",
            },
        )

        assert r.status_code == 200
        assert msgpack.unpackb(r.content) == {"message": "Hello, World!"}


@pytest.mark.asyncio
async def test_streaming_opt_in() -> None:
    chunk_size = 8
    request_data = {"message": "unpacked"}
    request_content = msgpack.packb(request_data)

    async def request_content_gen() -> AsyncIterator[bytes]:
        for i in range(0, len(request_content), chunk_size):
            yield request_content[i : min(i + chunk_size, len(request_content))]

    async def app(scope: Scope, receive: Receive, _send: Send) -> None:
        request = Request(scope, receive)
        await request.json()

    # No argument passed
    app = MessagePackMiddleware(app)

    async with _make_client(app) as client:
        with pytest.raises(NotImplementedError):
            _r = await client.post(
                "/",
                content=request_content_gen(),
                headers={"content-type": "application/vnd.msgpack"},
            )
