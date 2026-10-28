"""Agent interface: the turn loop only talks to agents through this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ContextFull(Exception):
    """The agent's context cannot hold another reply; the episode stops."""


@dataclass(frozen=True)
class AgentReply:
    text: str          # the message as kept in the conversation (notes + call)
    call: str | dict   # the single tool call to execute
    thinking: str = ""                                   # discarded after the reply; logged only
    meta: dict[str, Any] = field(default_factory=dict)   # model call details (tokens, timing, ...)


class Agent(ABC):
    """Keeps its conversation as a list of messages; one call per reply."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def observe(self, content: str) -> None:
        """A message from the environment or the user."""
        self.messages.append({"role": "user", "content": content})

    def respond(self) -> AgentReply:
        reply = self._reply()
        self.messages.append({"role": "assistant", "content": reply.text})
        return reply

    @abstractmethod
    def _reply(self) -> AgentReply:
        """Produce the next reply from self.messages."""

    def info(self) -> dict[str, Any]:
        """Setup details recorded in params.json."""
        return {}

    def state(self) -> dict:
        """Everything needed to continue after a restore (for checkpoints)."""
        return {"messages": [dict(m) for m in self.messages]}

    def load_state(self, data: dict) -> None:
        self.messages = [dict(m) for m in data["messages"]]
