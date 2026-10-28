import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import main as main_module
from agents.base import ContextFull
from LLM.agent import LLMAgent, merge_consecutive
from LLM.client import ChatClient, Completion, ServerError, split_thinking
from LLM.parsing import extract_call
from main import main

# --- parsing ------------------------------------------------------------------


def test_call_after_notes():
    call, kept = extract_call('Notes: plant elderberry.\n{"action": "plant", "plots": {"1": "elderberry"}}')
    assert call == {"action": "plant", "plots": {"1": "elderberry"}}
    assert kept == 'Notes: plant elderberry.\n{"action": "plant", "plots": {"1": "elderberry"}}'


def test_text_after_the_call_is_cut():
    text = 'Gather now.\n{"action": "gather"}\nGathered: +2 elderberry.\n[Turn 5]\n{"action": "skip"}'
    call, kept = extract_call(text)
    assert call == {"action": "gather"} and kept == 'Gather now.\n{"action": "gather"}'


def test_fenced_call_keeps_a_closed_fence():
    call, kept = extract_call('Check.\n```json\n{"tool": "inventory"}\n```\nmore')
    assert call == {"tool": "inventory"} and kept == 'Check.\n```json\n{"tool": "inventory"}\n```'


def test_braces_in_notes_are_skipped():
    call, _ = extract_call('Best so far {elderberry: 2} gave 5%; {"elderberry": 2} too.\n{"action": "brew", "recipe": {"elderberry": 3}}')
    assert call == {"action": "brew", "recipe": {"elderberry": 3}}


def test_object_without_action_is_passed_on_for_the_dispatcher():
    call, kept = extract_call('Brew {"recipe": {"mint": 1}} done')
    assert call == {"recipe": {"mint": 1}} and kept == 'Brew {"recipe": {"mint": 1}}'


def test_no_json_returns_the_text():
    assert extract_call("  I will think more.  ") == ("I will think more.", "I will think more.")


def test_split_thinking_fallback():
    assert split_thinking("<think>\nhmm\n</think>\nNotes {}", "") == ("Notes {}", "hmm")
    assert split_thinking("Notes", " given ") == ("Notes", "given")


# --- agent ------------------------------------------------------------------------


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def complete(self, messages, seed):
        self.requests.append((messages, seed))
        content, reasoning = self.replies.pop(0)
        return Completion(content, reasoning, "stop", {"prompt_tokens": 10, "completion_tokens": 5}, 0.1)

    def server_info(self):
        return {"n_ctx": 1000}


def test_merge_consecutive():
    merged = merge_consecutive([
        {"role": "user", "content": "a"}, {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c"}, {"role": "user", "content": "d"},
    ])
    assert merged == [{"role": "user", "content": "a\n\nb"}, {"role": "assistant", "content": "c"},
                      {"role": "user", "content": "d"}]


def test_thinking_is_never_kept_and_seeds_advance():
    client = FakeClient([('Notes A\n{"tool": "inventory"}\nplants: invented', "secret 1"),
                         ('Notes B\n{"action": "skip"}', "secret 2")])
    agent = LLMAgent(client, "SYSTEM", seed=100)
    agent.observe("opening")
    agent.observe("[Turn 1]")
    first = agent.respond()
    assert first.thinking == "secret 1" and first.call == {"tool": "inventory"}
    assert first.meta["raw_content"].endswith("plants: invented") and first.meta["call_index"] == 1
    agent.observe("plants: none")
    agent.respond()

    sent, seed = client.requests[1]
    assert seed == 101 and client.requests[0][1] == 100
    assert sent[0] == {"role": "system", "content": "SYSTEM"}
    assert sent[1] == {"role": "user", "content": "opening\n\n[Turn 1]"}
    assert sent[2] == {"role": "assistant", "content": 'Notes A\n{"tool": "inventory"}'}
    assert "secret" not in json.dumps(agent.state())


def test_state_round_trip():
    agent = LLMAgent(FakeClient([('{"action": "skip"}', "")]), "SYSTEM", seed=1)
    agent.observe("x")
    agent.respond()
    other = LLMAgent(FakeClient([]), "changed prompt file", seed=1)
    other.load_state(agent.state())
    assert other.messages == agent.messages and other.calls == 1 and other.system_prompt == "SYSTEM"


# --- client against a fake server --------------------------------------------------


@pytest.fixture
def server():
    """A one-route server; set .responses to a list of (status, body) and read .bodies."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            srv.bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            status, body = srv.responses.pop(0)
            self._send(status, body)

        def do_GET(self):
            self._send(200, {"model_path": "/m.gguf", "build_info": "b1",
                             "default_generation_settings": {"n_ctx": 4096, "params": {"temperature": 1.0, "top_p": 1.0}}})

        def _send(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    srv.bodies, srv.responses = [], []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.url = f"http://127.0.0.1:{srv.server_port}"
    yield srv
    srv.shutdown()


def ok(content, reasoning=""):
    return 200, {"choices": [{"message": {"content": content, "reasoning_content": reasoning}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 7, "completion_tokens": 3}}


def test_client_request_and_reply(server):
    server.responses = [ok("Notes {}", "think")]
    client = ChatClient(server.url, "m", max_tokens=99, thinking=True)
    result = client.complete([{"role": "user", "content": "hi"}], seed=4)
    assert (result.content, result.reasoning, result.usage["prompt_tokens"]) == ("Notes {}", "think", 7)
    body = server.bodies[0]
    assert body["chat_template_kwargs"] == {"enable_thinking": True, "preserve_thinking": False}
    assert body["seed"] == 4 and body["max_tokens"] == 99
    assert "temperature" not in body and "top_p" not in body  # the model's defaults apply


def test_client_overrides_and_server_info(server):
    server.responses = [ok("x")]
    client = ChatClient(server.url, "m", 10, temperature=0.6, top_p=0.95, thinking=False, reasoning_effort="medium")
    client.complete([], seed=0)
    assert server.bodies[0]["temperature"] == 0.6
    assert server.bodies[0]["chat_template_kwargs"] == {"enable_thinking": False, "preserve_thinking": False,
                                                        "reasoning_effort": "medium"}
    assert client.server_info() == {"url": server.url, "model_path": "/m.gguf", "n_ctx": 4096, "build_info": "b1",
                                    "default_sampling": {"temperature": 1.0, "top_p": 1.0}}


def test_client_errors(server):
    client = ChatClient(server.url, "m", 10, retry_delays=(0,))
    server.responses = [(400, {"error": {"type": "exceed_context_size_error",
                                         "message": "the request exceeds the available context size"}})]
    with pytest.raises(ContextFull):
        client.complete([], seed=0)
    server.responses = [(400, {"error": {"message": "bad field"}})]
    with pytest.raises(ServerError, match="bad field"):
        client.complete([], seed=0)
    server.responses = [(503, {"error": "loading"}), ok("after retry")]
    assert client.complete([], seed=0).content == "after retry"


def test_unreachable_server():
    client = ChatClient("http://127.0.0.1:9", "m", 10, retry_delays=())
    with pytest.raises(ConnectionError, match="unreachable"):
        client.complete([], seed=0)
    assert client.server_info() == {}


# --- full episodes with a scripted model ------------------------------------------


def run_llm_episode(tmp_path, monkeypatch, script, turn_cap="6"):
    prompt = tmp_path / "system.txt"
    prompt.write_text("SYSTEM PROMPT", encoding="utf-8")

    class ScriptedClient(FakeClient):
        def __init__(self, *args, **kwargs):
            super().__init__([])

        def complete(self, messages, seed):
            return script(messages, seed)

    monkeypatch.setattr(main_module, "ChatClient", ScriptedClient)
    return main([
        "--agent", "llm", "--llm-name", "fake/model", "--prompt-file", str(prompt),
        "--env-seed", "3", "--llm-seed", "5", "--turn-cap", turn_cap, "--garden-size", "4", "--goals", "target:I:10",
        "--runs-dir", str(tmp_path / "runs"), "--temp-dir", str(tmp_path / "temp"),
    ])


def test_llm_episode_outputs(tmp_path, monkeypatch):
    def script(messages, seed):
        if messages[-1]["content"].startswith("plants:"):
            return Completion('Nothing to brew.\n{"action": "skip"}', "private", "stop", {"prompt_tokens": 1}, 0.0)
        return Completion('Notes.\n{"tool": "inventory"}\nplants: made up', "private", "stop", {"prompt_tokens": 1}, 0.0)

    out = run_llm_episode(tmp_path, monkeypatch, script)
    calls = [json.loads(line) for line in (out.dir / "llm_calls.jsonl").read_text().splitlines()]
    assert len(calls) == 12 and calls[-1]["call_index"] == 12 and calls[0]["raw_content"].endswith("made up")
    transcript = (out.dir / "transcript.md").read_text()
    assert "agent (thinking, discarded)" in transcript and "plants: made up" not in transcript
    params = json.loads((out.dir / "params.json").read_text())
    assert params["system_prompt"] == "SYSTEM PROMPT" and params["llm_server"] == {"n_ctx": 1000}
    assert params["temperature"] is None and params["thinking"] is True
    checkpoint = (out.temp / "checkpoint.json").read_text()
    assert "private" not in checkpoint and "made up" not in checkpoint
    assert json.loads((out.dir / "summary.json").read_text())["stop_reason"] is None


def test_full_context_stops_the_episode(tmp_path, monkeypatch):
    def script(messages, seed):
        if seed >= 5 + 3:
            raise ContextFull("the request exceeds the available context size")
        return Completion('{"action": "skip"}', "", "stop", {}, 0.0)

    out = run_llm_episode(tmp_path, monkeypatch, script, turn_cap="20")
    summary = json.loads((out.dir / "summary.json").read_text())
    assert summary["stop_reason"] == "context full" and summary["turns_played"] == 3
    assert "Episode stopped: the context is full" in (out.dir / "transcript.md").read_text()
