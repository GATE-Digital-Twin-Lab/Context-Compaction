"""Agent interface: the turn loop only talks to agents through this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentReply:
    text: str          # the full message as written (reasoning + call)
    call: str | dict   # the single tool call to execute


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

    def state(self) -> dict:
        """Everything needed to continue after a restore (for checkpoints)."""
        return {"messages": [dict(m) for m in self.messages]}

    def load_state(self, data: dict) -> None:
        self.messages = [dict(m) for m in data["messages"]]
