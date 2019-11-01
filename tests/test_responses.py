import msgpack
import httpx

from msgpack_asgi.responses import MessagePackResponse


def test_msgpack_response() -> None:
    content = {"message": "Hello, world!"}
    app = MessagePackResponse(content=content)

    with httpx.Client(app=app, base_url="http://testserver") as client:
        r = client.get("/")

    assert r.headers["content-type"] == "application/x-msgpack"
    assert int(r.headers["content-length"]) == len(msgpack.packb(content))
    assert msgpack.unpackb(r.content, raw=False) == content
