from starlette.types import Message


async def mock_receive() -> Message:
    raise NotImplementedError  # pragma: no cover


async def mock_send(message: Message) -> None:
    raise NotImplementedError  # pragma: no cover
