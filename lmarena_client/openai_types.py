from __future__ import annotations
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


# -----------------------------
# Request models (minimal)
# -----------------------------

class ImageURL(BaseModel):
    url: str


class ContentPart(BaseModel):
    type: str
    text: Optional[str] = None
    image_url: Optional[ImageURL] = None


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = "user"
    content: Union[str, list[ContentPart]]


class ConversationRef(BaseModel):
    evaluationSessionId: str


class ChatCompletionsRequest(BaseModel):
    model: str = ""
    messages: list[Message]
    stream: bool = False

    # vendor extensions
    conversation: Optional[ConversationRef] = None
    conversation_id: Optional[str] = None


# -----------------------------
# Response models (minimal)
# -----------------------------

class ModelCard(BaseModel):
    id: str
    object: Literal["model"] = "model"
    owned_by: str = "lmarena"


class ListModelsResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelCard]


class ChatMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = None


class ChatCompletionsResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]

    # vendor extensions
    conversation: dict[str, Any] = Field(default_factory=dict)
    conversation_id: Optional[str] = None
    images: Optional[list[str]] = None
    usage: Optional[dict[str, Any]] = None


# -----------------------------
# Streaming response chunks
# -----------------------------

class Delta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: Delta = Field(default_factory=Delta)
    finish_reason: Optional[str] = None


class ChatCompletionsStreamChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]

    # vendor extensions (only used in final chunk)
    conversation: Optional[dict[str, Any]] = None
    conversation_id: Optional[str] = None
    images: Optional[list[str]] = None
    usage: Optional[dict[str, Any]] = None
