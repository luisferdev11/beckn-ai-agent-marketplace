"""
Tests for the orchestrator-compatible POST /task endpoint.

Contract under test:
  - URL:    POST /task?agent_id=<id>
  - Body:   the raw payload the agent expects (e.g. {"text": "..."})
  - 200 OK: { status, result, usage:{model_used, input_tokens, output_tokens, latency_ms} }
  - 404:    { status: "error", error: {code: "AGENT_NOT_FOUND"}, usage }
  - On agent ValueError → status="error", error.code="INVALID_INPUT"
"""


class TestHealth:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "agents-serg"
        # All 6 agents should be loaded
        assert set(body["agents"]) == {
            "summarizer-v1",
            "extractor-v1",
            "code-reviewer-v1",
            "translator-v1",
            "email-writer-v1",
            "sentiment-v1",
        }


class TestTaskEndpointSuccess:
    async def test_summarizer_returns_orchestrator_envelope(self, client):
        resp = await client.post(
            "/task",
            params={"agent_id": "summarizer-v1"},
            json={"text": "Long document about AI agents and standards.", "max_points": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["result"].startswith("FAKE_RESULT_")
        assert body["usage"]["model_used"]
        assert body["usage"]["output_tokens"] == 42
        assert isinstance(body["usage"]["latency_ms"], int)

    async def test_code_reviewer_works_on_separate_id(self, client):
        resp = await client.post(
            "/task",
            params={"agent_id": "code-reviewer-v1"},
            json={"code": "def f(x): return x+1", "language": "python"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["result"].startswith("FAKE_RESULT_")


class TestTaskEndpointErrors:
    async def test_unknown_agent_returns_404_envelope(self, client):
        resp = await client.post(
            "/task",
            params={"agent_id": "nonexistent-v1"},
            json={"text": "anything"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == "AGENT_NOT_FOUND"
        # Usage envelope must still be present so the orchestrator can parse
        assert "usage" in body

    async def test_invalid_payload_returns_invalid_input(self, client):
        # Summarizer raises ValueError when 'text' is empty
        resp = await client.post(
            "/task",
            params={"agent_id": "summarizer-v1"},
            json={"text": ""},
        )
        assert resp.status_code == 200  # body envelope expresses the error
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == "INVALID_INPUT"


class TestRunEndpointStillWorks:
    async def test_legacy_run_endpoint_intact(self, client):
        resp = await client.post(
            "/run",
            json={
                "agent_id": "summarizer-v1",
                "task_type": "summarize",
                "payload": {"text": "Some text"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["result"].startswith("FAKE_RESULT_")
