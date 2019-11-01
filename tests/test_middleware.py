import msgpack
import httpx

from msgpack_asgi.middleware import MsgPackMiddleware
from tests.utils import msgpack_app


def test_decode_response() -> None:
    app = MsgPackMiddleware(msgpack_app)
    with httpx.Client(app=app) as client:
        r = client.get("http://testserver")
        assert r.headers["content-type"] == "application/x-msgpack"
        data = msgpack.unpackb(r.content, raw=False)
        assert data == {"message": "Hello, world!"}
