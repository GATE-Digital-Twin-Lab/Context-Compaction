"""LLM agent: sends the conversation to the model; only the visible reply is kept."""

from typing import Any

from agents.base import Agent, AgentReply
from LLM.client import ChatClient
from LLM.parsing import extract_call


def merge_consecutive(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Join back-to-back messages of one role (an action's result and the next turn's header)."""
    merged: list[dict[str, str]] = []
    for m in messages:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1] = {"role": m["role"], "content": merged[-1]["content"] + "\n\n" + m["content"]}
        else:
            merged.append(dict(m))
    return merged


class LLMAgent(Agent):
    """Thinking is dropped from every reply; only the notes and the call stay in the conversation."""

    def __init__(self, client: ChatClient, system_prompt: str, seed: int) -> None:
        super().__init__()
        self.client = client
        self.system_prompt = system_prompt
        self.seed = seed
        self.calls = 0  # model calls so far; call k uses seed + k, so a replayed turn samples the same

    def request(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": self.system_prompt}] + merge_consecutive(self.messages)

    def _reply(self) -> AgentReply:
        completion = self.client.complete(self.request(), seed=self.seed + self.calls)
        self.calls += 1
        call, kept = extract_call(completion.content)
        meta = {
            "call_index": self.calls,
            "finish_reason": completion.finish_reason,
            "seconds": completion.seconds,
            "usage": completion.usage,
            "thinking_chars": len(completion.reasoning),
            "content_chars": len(completion.content),
            "kept_chars": len(kept),
            "raw_content": completion.content,
        }
        return AgentReply(kept, call, thinking=completion.reasoning, meta=meta)

    def info(self) -> dict[str, Any]:
        return {"system_prompt": self.system_prompt, "llm_server": self.client.server_info()}

    def state(self) -> dict:
        return {**super().state(), "system_prompt": self.system_prompt, "calls": self.calls}

    def load_state(self, data: dict) -> None:
        super().load_state(data)
        self.system_prompt = data["system_prompt"]
        self.calls = data["calls"]
