from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Usage:
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    @staticmethod
    def from_lmarena(d: dict[str, Any]) -> "Usage":
        # LMArena may return different naming depending on backend; keep flexible.
        prompt = d.get("promptTokens") or d.get("input_tokens") or d.get("promptTokenCount") or d.get("prompt_tokens")
        completion = d.get("completionTokens") or d.get("output_tokens") or d.get("candidatesTokenCount") or d.get("completion_tokens")
        total = d.get("totalTokenCount") or d.get("total_tokens")
        if total is None and prompt is not None and completion is not None:
            try:
                total = int(prompt) + int(completion)
            except Exception:
                total = None
        return Usage(
            prompt_tokens=int(prompt) if prompt is not None else None,
            completion_tokens=int(completion) if completion is not None else None,
            total_tokens=int(total) if total is not None else None,
        )


@dataclass(frozen=True)
class StreamFinal:
    evaluation_session_id: str
    finish_reason: Optional[str] = None
    usage: Optional[Usage] = None


@dataclass(frozen=True)
class StreamImages:
    urls: list[str]
