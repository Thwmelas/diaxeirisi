"""Ollama client for the LLM Decision-Making Module.

Callable object: client(prompt) -> response text, which is exactly what
LLMDecisionMaker expects as llm_client. Standard library only.

Setup:
    1. Install Ollama (https://ollama.com/download)
    2. ollama pull llama3.2:3b

Environment variables (optional):
    OLLAMA_URL      default http://localhost:11434
    OLLAMA_MODEL    default llama3.2:3b
    OLLAMA_TIMEOUT  seconds, default 20
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class LLMUnavailable(RuntimeError):
    """The model server could not be reached or returned an error."""


class OllamaClient:
    def __init__(self, model: Optional[str] = None, url: Optional[str] = None,
                 timeout: Optional[float] = None, json_schema: Optional[Dict[str, Any]] = None,
                 temperature: float = 0.0, max_tokens: int = 120):
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.url = (url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.timeout = float(timeout or os.getenv("OLLAMA_TIMEOUT", "20"))
        self.json_schema = json_schema
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def __call__(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema or self.json_schema or "json",
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
            "keep_alive": "30m",  # keep the model in memory between decisions
        }
        request = urllib.request.Request(
            f"{self.url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise LLMUnavailable(f"Ollama HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMUnavailable(f"Cannot reach Ollama at {self.url}: {exc}") from exc
        try:
            return body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMUnavailable(f"Unexpected Ollama response: {str(body)[:200]}") from exc

    def warm_up(self) -> bool:
        """Load the model into memory (the first call can take 10-20 s)."""
        old_timeout, self.timeout = self.timeout, max(self.timeout, 120.0)
        try:
            self('Reply with {"ok": true}')
            return True
        except LLMUnavailable:
            return False
        finally:
            self.timeout = old_timeout

    def is_available(self) -> bool:
        """True if the server is up and the model has been pulled."""
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=3) as response:
                tags = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return False
        names = {m.get("name", "") for m in tags.get("models", [])}
        return any(n == self.model or n.split(":")[0] == self.model for n in names)
