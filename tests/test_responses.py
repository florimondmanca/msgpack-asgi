import httpx
import msgpack
import pytest

from msgpack_asgi import MessagePackResponse


@pytest.mark.asyncio
async def test_msgpack_response() -> None:
    content = {"message": "Hello, world!"}
    app = MessagePackResponse(content=content)

    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        r = await client.get("/")

    assert r.headers["content-type"] == "application/x-msgpack"
    assert int(r.headers["content-length"]) == len(msgpack.packb(content))
    assert msgpack.unpackb(r.content, raw=False) == content
