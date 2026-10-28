"""Chat client for an OpenAI-compatible server (llama-server; vLLM or Ollama work the same way)."""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from agents.base import ContextFull

RETRY_DELAYS = (5, 15, 45)  # seconds between attempts after a connection or server error


class ServerError(Exception):
    """The server rejected the request (not retried)."""


@dataclass(frozen=True)
class Completion:
    content: str        # the visible reply
    reasoning: str      # the thinking, separated by the server
    finish_reason: str | None
    usage: dict[str, Any]
    seconds: float


def split_thinking(content: str, reasoning: str) -> tuple[str, str]:
    """Fallback when the server leaves '<think>...</think>' inside the content."""
    if not reasoning and "</think>" in content:
        head, content = content.split("</think>", 1)
        reasoning = head.replace("<think>", "", 1)
    return content.strip(), reasoning.strip()


def is_context_overflow(status: int, body: str) -> bool:
    text = body.lower()
    return status == 400 and "context" in text and ("exceed" in text or "too long" in text)


class ChatClient:
    """Sends the whole conversation each call; sampling not given here is left to the server's defaults."""

    def __init__(
        self,
        url: str,
        model: str,
        max_tokens: int,
        temperature: float | None = None,
        top_p: float | None = None,
        thinking: bool = True,
        timeout: float = 3600,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
    ) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.thinking = thinking
        self.timeout = timeout
        self.retry_delays = retry_delays

    def payload(self, messages: list[dict[str, str]], seed: int) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "seed": seed,
            "chat_template_kwargs": {"enable_thinking": self.thinking},
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.top_p is not None:
            body["top_p"] = self.top_p
        return body

    def complete(self, messages: list[dict[str, str]], seed: int) -> Completion:
        """Raises ContextFull if the conversation no longer fits, ServerError on other rejections."""
        start = time.monotonic()
        data = self._post("/v1/chat/completions", self.payload(messages, seed))
        choice = data["choices"][0]
        message = choice["message"]
        content, reasoning = split_thinking(message.get("content") or "", message.get("reasoning_content") or "")
        return Completion(content, reasoning, choice.get("finish_reason"), data.get("usage", {}),
                          round(time.monotonic() - start, 2))

    def server_info(self) -> dict[str, Any]:
        """What the server reports about itself (llama-server's /props); empty if unavailable."""
        try:
            with urllib.request.urlopen(self.url + "/props", timeout=30) as response:
                props = json.loads(response.read())
        except (urllib.error.URLError, OSError, ValueError):
            return {}
        settings = props.get("default_generation_settings", {})
        params = settings.get("params", {})
        sampling = {k: params[k] for k in ("temperature", "top_p", "top_k", "min_p") if k in params}
        return {
            "url": self.url,
            "model_path": props.get("model_path"),
            "n_ctx": settings.get("n_ctx"),
            "build_info": props.get("build_info"),
            "default_sampling": sampling,
        }

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        for attempt, delay in enumerate((*self.retry_delays, None)):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as err:
                text = err.read().decode(errors="replace")
                if is_context_overflow(err.code, text):
                    raise ContextFull(text) from None
                if err.code < 500 or delay is None:
                    raise ServerError(f"HTTP {err.code}: {text}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
                if delay is None:
                    raise ConnectionError(f"Model server unreachable at {self.url}: {err}") from None
            time.sleep(delay)
        raise AssertionError("unreachable")
