from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openv.default_config import TRACE_PATH, ensure_app_dirs

try:
    import tiktoken
except ImportError:  # pragma: no cover - optional dependency
    tiktoken = None


@dataclass(slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Scribe:
    def __init__(self, trace_path: Path = TRACE_PATH) -> None:
        self.trace_path = trace_path
        ensure_app_dirs()

    def _encoder_for_model(self, model: str):
        if tiktoken is None:
            return None
        try:
            if "mistral" in model.lower() or "llama" in model.lower():
                return tiktoken.get_encoding("cl100k_base")
            return tiktoken.encoding_for_model(model)
        except Exception:
            return tiktoken.get_encoding("cl100k_base")

    def estimate_tokens(self, text: str, model: str) -> int:
        encoder = self._encoder_for_model(model)
        if encoder is None:
            return max(1, len(text) // 4)
        return len(encoder.encode(text))

    def record_usage(self, prompt: str, completion: str, model: str) -> TokenUsage:
        usage = TokenUsage(
            prompt_tokens=self.estimate_tokens(prompt, model),
            completion_tokens=self.estimate_tokens(completion, model),
        )
        return usage

    def log_json_request(self, endpoint: str, payload: dict[str, Any]) -> None:
        ensure_app_dirs()
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "payload": payload,
        }
        with self.trace_path.open("a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(record, ensure_ascii=False) + "\n")
