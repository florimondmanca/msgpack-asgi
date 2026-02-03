# msgpack-asgi

[![Build Status](https://dev.azure.com/florimondmanca/public/_apis/build/status/florimondmanca.msgpack-asgi?branchName=master)](https://dev.azure.com/florimondmanca/public/_build?definitionId=5)
[![Coverage](https://codecov.io/gh/florimondmanca/msgpack-asgi/branch/master/graph/badge.svg)](https://codecov.io/gh/florimondmanca/msgpack-asgi)
[![Package version](https://badge.fury.io/py/msgpack-asgi.svg)](https://pypi.org/project/msgpack-asgi)

`msgpack-asgi` allows you to add automatic [MessagePack](https://msgpack.org/) content negotiation to ASGI applications (Starlette, FastAPI, Quart, etc.), with a single line of code:

```python
app.add_middleware(MessagePackMiddleware)
```

_(Adapt this snippet to your framework-specific middleware API.)_

This gives you the bandwitdth usage reduction benefits of MessagePack without having to change existing code.

**Note**: this comes at a CPU usage cost, since `MessagePackMiddleware` will perform MsgPack decoding while your application continues to decode and encode JSON data (see also [How it works](#how-it-works)). If your use case is CPU-sensitive, rather than strictly focused on reducing network bandwidth, this package may not be for you.

## Installation

Install with pip:

```bash
pip install "msgpack-asgi==3.*"
```

**Be sure to pin to the latest major version**, as above. Breaking changes may occur across major versions. If so, details on migration steps will be provided in CHANGELOG.md.

## Quickstart

First, you'll need an ASGI application. Let's use this sample application, which exposes an endpoint that returns JSON data:

```python
# For convenience, we use some ASGI components from Starlette.
# Install with: `$ pip install starlette`.
from starlette.requests import Request
from starlette.responses import JSONResponse


async def get_response(request):
    if request.method == "POST":
        data = await request.json()
        return JSONResponse({"data": data}, status_code=201)
    else:
        return JSONResponse({"message": "Hello, msgpack!"})


async def app(scope, receive, send):
    assert scope["type"] == "http"
    request = Request(scope=scope, receive=receive)
    response = await get_response(request)
    await response(scope, receive, send)
```

Then, wrap your application around `MessagePackMiddleware`:

```python
from msgpack_asgi import MessagePackMiddleware

app = MessagePackMiddleware(app)
```

Serve your application using an ASGI server, for example with [Uvicorn](https://www.uvicorn.org):

```bash
uvicorn app:app
```

Now, let's make a request that accepts MessagePack data in response:

```bash
curl -i http://localhost:8000 -H "Accept: application/vnd.msgpack"
```

You should get the following output:

```http
HTTP/1.1 200 OK
date: Fri, 01 Nov 2019 17:40:14 GMT
server: uvicorn
content-length: 25
content-type: application/vnd.msgpack

��message�Hello, msgpack!
```

What happened? Since we told the application that we accepted MessagePack-encoded responses, `msgpack-asgi` automatically converted the JSON data returned by the Starlette application to MessagePack.

We can make sure the response contains valid MessagePack data by making the request again in Python, and decoding the response content:

```python
>>> import requests
>>> import msgpack
>>> url = "http://localhost:8000"
>>> headers = {"accept": "application/vnd.msgpack"}
>>> r = requests.get(url, headers=headers)
>>> r.content
b'\x81\xa7message\xafHello, msgpack!'
>>> msgpack.unpackb(r.content, raw=False)
{'message': 'Hello, msgpack!'}
```

`msgpack-asgi` also works in reverse: it will automatically decode MessagePack-encoded data sent by the client to JSON. We can try this out by making a `POST` request to our sample application with a MessagePack-encoded body:

```python
>>> import requests
>>> import msgpack
>>> url = "http://localhost:8000"
>>> data = msgpack.packb({"message": "Hi, there!"})
>>> headers = {"content-type": "application/vnd.msgpack"}
>>> r = requests.post(url, data=data, headers=headers)
>>> r.json()
{'data': {'message': 'Hi, there!'}}
```

That's all there is to it! You can now go reduce the size of your payloads.

## Advanced usage

### Custom implementations

`msgpack-asgi` supports customizing the default encoding/decoding implementation. This is useful for fine-tuning application performance via an alternative msgpack implementation for encoding, decoding, or both.

To do so, use the following arguments:

* `packb` - _(Optional, type: `(obj: Any) -> bytes`, default: `msgpack.packb`)_ - Used to encode outgoing data.
* `unpackb` - _(Optional, type: `(data: bytes) -> Any`, default: `msgpack.unpackb`)_ - Used to decode incoming data.

For example, to use the [`ormsgpack`](https://pypi.org/project/ormsgpack/) library for encoding:

```python
import ormsgpack  # Installed separately.
from msgpack_asgi import MessagePackMiddleware

def packb(obj):
    option = ...  # See `ormsgpack` options.
    return ormsgpack.packb(obj, option=option)

app = MessagePackMiddleware(..., packb=packb)
```

## Streaming requests or responses

By default `msgpack-asgi` will raise a `NotImplementedError` if encountering a streaming request or response body.

This is because the full request and response body content has to be loaded in memory before it can be re-encoded.

You can opt into naive (buffered) request or response streaming by passing `allow_naive_streaming=True` to the middleware.

Be aware that this will induce large RAM usage for large request or response bodies. You may want to look into setting or tweaking request or response limits on your ASGI or frontend web server.

## How it works

![](https://github.com/florimondmanca/msgpack-asgi/blob/master/img/msgpack-asgi.png)

An ASGI application wrapped around `MessagePackMiddleware` will perform automatic content negotiation based on the client's capabilities. More precisely:

- If the client sends MessagePack-encoded data with the `application/vnd.msgpack` content type, `msgpack-asgi` will automatically re-encode the body to JSON and re-write the request `Content-Type` to `application/json` for your application to consume. (Note: this means applications will not be able to distinguish between MessagePack and JSON client requests.)
- If the client sent the `Accept: application/vnd.msgpack` header, `msgpack-asgi` will automatically re-encode any JSON response data to MessagePack for the client to consume.

(In other cases, `msgpack-asgi` won't intervene at all. NOTE: the content type to look for can be customized -- see API Reference below.)

## API Referece

### `MessagePackMiddleware`

**Signature**:

```python
MessagePackMiddleware(
    app,
    *,
    packb=msgpack.packb,
    unpackb=msgpack.packb,
    content_type="application/vnd.msgpack"
)
```

**Parameters described**:

* `app`: an ASGI app to add msgpack support to
* `packb` - callable (Optional, Added in 1.1.0): msgpack encoding function. Defaults to `msgpack.packb`.
* `unpackb` - callable _(Optional, Added in 1.1.0)_: msgpack decoding function. Defaults to `msgpack.unpackb`.
* `content_type` - str _(Optional, Added in 2.0.0)_: the content type (_a.k.a_ MIME type) to use for detecting incoming msgpack requests or sending msgpack responses. Defaults to the IANA-registered `application/vnd.msgpack` MIME type. Use this option when working with older systems that send or expect e.g. `application/x-msgpack`.
* `allow_naive_streaming` - bool _(Optional, Added in 3.0.0)_: whether to allow encoding/decoding streaming request or response body data by buffering it up into memory. Defaults to `False`.

## License

MIT
