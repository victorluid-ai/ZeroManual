from __future__ import annotations

import json
import os
from typing import Any

import anthropic
from dotenv import load_dotenv


class ClaudeClient:
    def __init__(self) -> None:
        load_dotenv()
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        self.default_max_tokens = int(os.getenv("CLAUDE_MAX_TOKENS", "256"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def complete_text(self, system: str, user: str, max_tokens: int | None = None) -> str | None:
        if not self.enabled:
            return None
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            message = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return message.content[0].text.strip() if message.content else None
        except anthropic.APIError:
            return None

    def complete_json(self, system: str, user: str, max_tokens: int | None = None) -> dict[str, Any] | None:
        text = self.complete_text(system=system, user=user, max_tokens=max_tokens)
        if not text or "{" not in text:
            return None
        start = text.index("{")
        end = text.rindex("}") + 1
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            return None
