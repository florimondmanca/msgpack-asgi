# msgpack-asgi

MsgPack support for ASGI applications and frameworks.

`msgpack-asgi` provides support for:

- Encoding msgpack-encoded 
## Usage

Synopsis:

```python
from msgpack_asgi.middleware import MsgPackMiddleware

app: "ASGIApp"
app = MsgPackMiddleware(app)
```

Starlette example:

```python
from starlette.applications import Starlette
from msgpack_asgi.middleware import MsgPackMiddleware

app = Starlette()
app.add_middleware(MsgPackMiddleware)

@app.route("/")
async def home(request):
    body = msgpack.packb({"message": "Hello, msgpack!"})
    return PlainTextResponse(body, media_type="application/x-msgpack")
```

```bash
curl http://localhost:8000 -i
```

```http
```
