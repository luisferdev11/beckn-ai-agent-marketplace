import os

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app(monkeypatch):
    # Prevent any accidental real LLM call in tests
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-used")

    fake_calls = []

    def _fake_call_llm(prompt, system=""):
        fake_calls.append({"prompt": prompt, "system": system})
        return ("FAKE_RESULT_" + str(len(fake_calls)), 42)

    # Patch every agent's call_llm reference so no agent hits the network.
    import core.llm as llm_module

    monkeypatch.setattr(llm_module, "call_llm", _fake_call_llm)

    # Re-bind on each agent module (they imported call_llm directly)
    import agents.summarizer as a_summarizer
    import agents.code_reviewer as a_reviewer
    import agents.translator as a_translator
    import agents.email_writer as a_email
    import agents.sentiment as a_sentiment
    import agents.extractor as a_extractor

    for mod in (a_summarizer, a_reviewer, a_translator, a_email, a_sentiment, a_extractor):
        monkeypatch.setattr(mod, "call_llm", _fake_call_llm)

    # Always reload main with the patches in place
    import importlib
    import main as main_module

    importlib.reload(main_module)
    return main_module.app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
