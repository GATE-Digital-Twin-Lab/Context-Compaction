from utils import clean_transcript, clean_transcripts

TRANSCRIPT = """# Transcript — llm — 1

## Turn 1

**user**

Goal: brew.

**environment**

[Turn 1]

**agent (thinking, discarded)**

Hmm.

**Plan** (bold, but not a role line)

**agent**

New facts: none.
{"action": "skip"}

**environment**

Skipped.

## Turn 2

**agent (thinking, discarded)**

Still thinking.

**agent**

{"action": "skip"}
"""


def test_clean_transcript_drops_only_the_thinking():
    clean = clean_transcript(TRANSCRIPT)
    assert clean.startswith("# Transcript — llm — 1 (clean)\n\nOnly what stays in the agent's context")
    assert "Hmm." not in clean and "Still thinking." not in clean and "**Plan**" not in clean
    assert "thinking, discarded)**" not in clean
    assert clean.endswith(
        "[Turn 1]\n\n**agent**\n\nNew facts: none.\n{\"action\": \"skip\"}\n\n**environment**\n\n"
        "Skipped.\n\n## Turn 2\n\n**agent**\n\n{\"action\": \"skip\"}\n"
    )


def test_main_writes_a_clean_transcript_for_every_run(tmp_path):
    for run in ("a/1", "b/2"):
        (tmp_path / run).mkdir(parents=True)
        (tmp_path / run / "transcript.md").write_text(TRANSCRIPT, encoding="utf-8")
    clean_transcripts([str(tmp_path)])
    assert all("Hmm." not in (tmp_path / run / "transcript_clean.md").read_text() for run in ("a/1", "b/2"))
