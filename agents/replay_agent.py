"""Replays the replies of a recorded run, e.g. to rebuild its exact state up to some turn."""

from collections import deque

from agents.base import Agent, AgentReply
from LLM.parsing import extract_call
from utils import THINKING_ROLE, transcript_blocks


def recorded_replies(transcript: str) -> list[AgentReply]:
    """Every agent reply of a transcript.md in order, with the thinking logged before it."""
    replies, thinking = [], ""
    for _, role, content in transcript_blocks(transcript):
        if role == THINKING_ROLE:
            thinking = content
        elif role == "agent":
            replies.append(AgentReply(content, extract_call(content)[0], thinking=thinking))
            thinking = ""
    return replies


class ReplayAgent(Agent):
    def __init__(self, replies: list[AgentReply]) -> None:
        super().__init__()
        self._replies = deque(replies)
        self.replayed = 0

    def _reply(self) -> AgentReply:
        if not self._replies:
            raise ValueError("The recorded run has no more replies.")
        self.replayed += 1
        return self._replies.popleft()
