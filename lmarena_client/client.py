from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from .config import ClientConfig
from .browser import BrowserManager
from .core import LMArenaCore, ChatResult
from .discovery import Discovery
from .stream import StreamFinal, StreamImages
from .utils import uuid7


@dataclass
class Conversation:
    evaluation_session_id: str


class ChatSession:
    def __init__(self, *, client: "Client", model: str, conversation: Conversation, is_new: bool) -> None:
        self._client = client
        self.model = model
        self.conversation = conversation
        self._is_new = is_new

    async def send(
        self,
        text: str,
        *,
        images: list[tuple[Any, Optional[str]]] | None = None,
        stream: bool = False,
        timeout: Optional[int] = None,
    ) -> ChatResult | AsyncIterator[str]:
        """
        Send a single user message.

        - stream=False: returns ChatResult
        - stream=True: returns AsyncIterator[str] yielding text deltas

        If this session was created via `client.chats.create()`, the first send uses
        the create-evaluation endpoint (create_new=True) while keeping the same id.
        """
        if not stream:
            result = await self._client._core.send_message(
                model=self.model,
                prompt=text,
                evaluation_session_id=self.conversation.evaluation_session_id,
                create_new=self._is_new,
                media=images,
                timeout=timeout,
            )
            # Keep the conversation id aligned with what the server confirms.
            self.conversation = Conversation(evaluation_session_id=result.evaluation_session_id)
            self._is_new = False
            return result

        async def _gen() -> AsyncIterator[str]:
            async for event in self._client._core.stream_message(
                model=self.model,
                prompt=text,
                evaluation_session_id=self.conversation.evaluation_session_id,
                create_new=self._is_new,
                media=images,
                timeout=timeout,
            ):
                if isinstance(event, str):
                    yield event
                elif isinstance(event, StreamImages):
                    # ignore by default for the text stream API
                    continue
                elif isinstance(event, StreamFinal):
                    # Update session state when the stream ends.
                    self.conversation = Conversation(evaluation_session_id=event.evaluation_session_id)
                    self._is_new = False

        return _gen()


class ChatsAPI:
    def __init__(self, client: "Client") -> None:
        self._client = client

    async def create(self, *, model: str) -> ChatSession:
        await self._client.bootstrap()
        # Allow callers to have an id immediately, but first send must use create-evaluation.
        eval_id = str(uuid7())
        return ChatSession(
            client=self._client,
            model=model,
            conversation=Conversation(evaluation_session_id=eval_id),
            is_new=True,
        )

    async def resume(self, *, model: str, chat_id: str) -> ChatSession:
        await self._client.bootstrap()
        return ChatSession(
            client=self._client,
            model=model,
            conversation=Conversation(evaluation_session_id=chat_id),
            is_new=False,
        )


class Client:
    """
    Library client.

    - bootstrap(): starts/bootstraps the browser and loads models/actions
    - list_models(): returns live list from LMArena
    - chats: create/resume chat sessions
    """

    def __init__(self, config: Optional[ClientConfig] = None) -> None:
        self.config = config or ClientConfig.from_env()
        self._browser = BrowserManager(self.config)
        self._discovery = Discovery(self._browser, origin=self.config.origin)
        self._core = LMArenaCore(self.config, self._browser, self._discovery)
        self.chats = ChatsAPI(self)
        self._bootstrapped = False

    async def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        await self._core.bootstrap()
        self._bootstrapped = True

    async def list_models(self) -> list[str]:
        await self.bootstrap()
        return await self._core.list_models()



