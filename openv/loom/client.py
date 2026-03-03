from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import json
import httpx

from openv.scribe.telemetry import Scribe


class LoomError(RuntimeError):
    pass


class LoomClient:
    def __init__(self, base_url: str, timeout: int, scribe: Scribe | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.scribe = scribe or Scribe()

    async def check_health(self) -> bool:
        endpoint = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(endpoint)
                response.raise_for_status()
            return True
        except Exception:
            return False

    async def chat_stream(
        self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        endpoint = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        self.scribe.log_json_request("/api/chat", payload)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", endpoint, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        yield json.loads(line)
        except Exception as exc:
            raise LoomError(f"Ollama chat request failed: {exc}") from exc

    async def generate_stream(
        self, model: str, prompt: str, system: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        endpoint = f"{self.base_url}/api/generate"
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": True}
        if system:
            payload["system"] = system
        self.scribe.log_json_request("/api/generate", payload)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", endpoint, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        yield json.loads(line)
        except Exception as exc:
            raise LoomError(f"Ollama generate request failed: {exc}") from exc
