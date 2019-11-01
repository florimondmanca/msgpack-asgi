import typing

import msgpack
from starlette.responses import Response


class MessagePackResponse(Response):
    media_type = "application/x-msgpack"

    def render(self, content: typing.Any) -> bytes:
        return msgpack.packb(content)
