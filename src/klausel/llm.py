"""Minimal client for a local Ollama server (no SDK, just HTTP)."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from klausel.config import get_settings


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self, base_url: str | None = None, model: str | None = None, timeout: float | None = None
    ):
        s = get_settings()
        self.base_url = (base_url or s.ollama_url).rstrip("/")
        self.model = model or s.ollama_model
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout or s.ollama_timeout_s)

    def ensure_model(self) -> None:
        try:
            tags = self._http.get("/api/tags").raise_for_status().json()
        except httpx.HTTPError as e:
            raise OllamaError(f"Ollama not reachable at {self.base_url}: {e}") from e
        names = {m["name"] for m in tags.get("models", [])}
        if self.model not in names and f"{self.model}:latest" not in names:
            raise OllamaError(f"Model '{self.model}' is not pulled. Run: ollama pull {self.model}")

    def chat(
        self, messages: list[dict[str, str]], *, temperature: float = 0.1, stream: bool = False
    ) -> Iterator[str]:
        """Yield response text (a single item when stream=False)."""
        body = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            # num_predict caps runaway answers from small models.
            "options": {"temperature": temperature, "num_ctx": 8192, "num_predict": 1024},
        }
        if not stream:
            r = self._http.post("/api/chat", json=body)
            if r.status_code != 200:
                raise OllamaError(f"Ollama error {r.status_code}: {r.text}")
            yield r.json()["message"]["content"]
            return
        with self._http.stream("POST", "/api/chat", json=body) as r:
            if r.status_code != 200:
                raise OllamaError(f"Ollama error {r.status_code}: {r.read().decode()}")
            for line in r.iter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if content := msg.get("message", {}).get("content"):
                    yield content
                if msg.get("done"):
                    break
