"""Summary compactor: the model summarises its own context, and the summary replaces the conversation."""

from dataclasses import dataclass
from pathlib import Path

from LLM.agent import merge_consecutive
from LLM.client import ChatClient, Completion

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
SUMMARY_PROMPT = PROMPTS / "summary.txt"
CONTINUE_PROMPT = PROMPTS / "summary_continue.txt"
SCOPE_ALL = "The summary below replaces all earlier messages."
SCOPE_EARLIER = "The summary below replaces the earlier messages; the most recent messages follow it unchanged."


@dataclass(frozen=True)
class Compaction:
    summarised: list[dict[str, str]]  # the messages the summary replaces
    after: list[dict[str, str]]       # the new conversation: the summary message plus the kept messages
    summary: str
    completion: Completion


def summarise(
    client: ChatClient, system_prompt: str, messages: list[dict[str, str]], seed: int,
    keep_last: int = 0, summary_prompt: Path = SUMMARY_PROMPT, continue_prompt: Path = CONTINUE_PROMPT,
) -> Compaction:
    """Summarise all but the last keep_last messages (same system prompt, the summary instruction as the
    last user message); the new conversation is the summary message followed by the kept messages."""
    if not 0 <= keep_last < len(messages):
        raise ValueError(f"keep_last must be in [0, {len(messages)}).")
    cut = len(messages) - keep_last
    summarised, kept = [dict(m) for m in messages[:cut]], [dict(m) for m in messages[cut:]]
    instruction = summary_prompt.read_text(encoding="utf-8").strip()
    request = [{"role": "system", "content": system_prompt}]
    request += merge_consecutive(summarised + [{"role": "user", "content": instruction}])
    completion = client.complete(request, seed=seed)
    summary = completion.content.strip()
    message = continue_prompt.read_text(encoding="utf-8").strip().format(
        scope=SCOPE_EARLIER if kept else SCOPE_ALL, summary=summary)
    return Compaction(summarised, [{"role": "user", "content": message}] + kept, summary, completion)
