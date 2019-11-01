# msgpack-asgi

Drop-in [MessagePack](https://msgpack.org/) support for ASGI applications and frameworks. `msgpack-asgi` gives you the performance benefits of MessagePack without having to change your existing code.

If you have a web API exchanging JSON data with the outside world, `msgpack-asgi` will automatically convert JSON data to MessagePack in order to save bandwitdth. For example:

- If the client sends MessagePack-encoded data, `msgpack-asgi` will automatically re-encode it to JSON for your application to consume.
- If the client supports receiving MessagePack-encoded responses, `msgpack-asgi` will automatically re-encode JSON response data to MessagePack.

(And in other cases, `msgpack-asgi` won't intervene at all.)

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

That's all there is to it!

## License

MIT
