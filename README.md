# msgpack-asgi

[![Build Status](https://travis-ci.com/florimondmanca/msgpack-asgi.svg?branch=master)](https://travis-ci.com/florimondmanca/msgpack-asgi)
[![Coverage](https://codecov.io/gh/florimondmanca/msgpack-asgi/branch/master/graph/badge.svg)](https://codecov.io/gh/florimondmanca/msgpack-asgi)
[![Package version](https://badge.fury.io/py/msgpack-asgi.svg)](https://pypi.org/project/msgpack-asgi)

`msgpack-asgi` allows you to add automatic [MessagePack](https://msgpack.org/) content negotiation to ASGI applications with a single line of code:

```python
app = MessagePackMiddleware(app)
```

This gives you the performance benefits of MessagePack (e.g. reduced bandwidth usage) without having to change existing code. See also [How it works](#how-it-works).

**Note**: this project is in an alpha stage.

## Installation

Install with pip:

```bash
pip install "mspack-asgi==0.*"
```

## Quickstart

First, you'll need an ASGI application. Let's use this sample [Starlette](https://www.starlette.io) application, which exposes an endpoint that returns JSON data:

```python
from starlette.applications import Starlette
from starlette.responses import JSONResponse

app = Starlette()


@app.route("/", methods=["GET", "POST"])
async def home(request):
    if request.method == "POST":
        data = await request.json()
        return JSONResponse({"data": data})
    else:
        return JSONResponse({"message": "Hello, msgpack!"})
```

Then, wrap your application around `MessagePackMiddleware`:

```python
from msgpack_asgi.middleware import MessagePackMiddleware

app.add_middleware(MessagePackMiddleware)
```

Serve your application using an ASGI server, for example with [Uvicorn](https://www.uvicorn.org):

```bash
uvicorn app:app
```

Now, let's make a request that accepts MessagePack data in response:

```bash
curl -i http://localhost:8000 -H "Accept: application/x-msgpack"
```

You should get the following output:

```http
HTTP/1.1 200 OK
date: Fri, 01 Nov 2019 17:40:14 GMT
server: uvicorn
content-length: 25
content-type: application/x-msgpack

��message�Hello, msgpack!
```

What happened? Since we told the application that we accepted MessagePack-encoded responses, `msgpack-asgi` automatically converted the JSON data returned by the Starlette application to MessagePack.

We can make sure the response contains valid MessagePack data by making the request again using [HTTPX](https://github.com/encode/httpx) (`$ pip install httpx`), and decoding the response content:

```python
>>> import httpx
>>> import msgpack
>>> url = "http://localhost:8000"
>>> headers = {"accept": "application/x-msgpack"}
>>> r = httpx.get(url, headers=headers)
>>> r.content
b'\x81\xa7message\xafHello, msgpack!'
>>> msgpack.unpackb(r.content, raw=False)
{'message': 'Hello, msgpack!'}
```

`msgpack-asgi` also works in reverse: it will automatically decode MessagePack-encoded data sent by the client to JSON. We can try this out by making a `POST` request to our sample application with a MessagePack-encoded body:

```python
>>> import httpx
>>> import msgpack
>>> url = "http://localhost:8000"
>>> data = msgpack.packb({"message": "Hi, there!"})
>>> headers = {"content-type": "application/x-msgpack"}
>>> r = httpx.post(url, data=data, headers=headers)
>>> r.json()
{'data': {'message': 'Hi, there!'}}
```

That's all there is to it! You can now go reduce the size of your payloads. :-)

## Limitations

`msgpack-asgi` does not support request or response streaming. This is because the full request and response body content has to be loaded in memory before it can be re-encoded.

## How it works

![](https://github.com/florimondmanca/msgpack-asgi/blob/master/img/msgpack-asgi.png)

An ASGI application wrapped around `MessagePackMiddleware` will perform automatic content negotiation based on the client's capabilities. More precisely:

- If the client sends MessagePack-encoded data with the `application/x-msgpack` content type, `msgpack-asgi` will automatically re-encode it to JSON for your application to consume.
- If the client sent the `Accept: application/x-msgpack` header, `msgpack-asgi` will automatically re-encode any JSON response data to MessagePack for the client to consume.

(In other cases, `msgpack-asgi` won't intervene at all.)

## License

MIT
