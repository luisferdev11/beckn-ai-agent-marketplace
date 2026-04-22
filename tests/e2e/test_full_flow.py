"""
E2E tests — run against the full Docker Compose stack.

Prerequisites:
  cd infra && docker compose up -d
  Wait for all services to be healthy.

These tests call the real services over HTTP. No mocks.
Run with: pytest tests/e2e/ --e2e

To skip in CI when Docker is not available, use:
  pytest tests/e2e/ -m e2e
"""

import time
import httpx
import pytest

pytestmark = pytest.mark.e2e

BAP_URL = "http://localhost:3001"
BPP_URL = "http://localhost:3002"
ORCHESTRATOR_URL = "http://localhost:3003"
AGENTS_URL = "http://localhost:3004"


@pytest.fixture(scope="session")
def http():
    return httpx.Client(timeout=30.0)


class TestServicesAreHealthy:
    def test_bap_is_healthy(self, http):
        r = http.get(f"{BAP_URL}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_bpp_is_healthy(self, http):
        r = http.get(f"{BPP_URL}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_orchestrator_is_healthy(self, http):
        r = http.get(f"{ORCHESTRATOR_URL}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_agents_is_healthy(self, http):
        r = http.get(f"{AGENTS_URL}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestCatalog:
    def test_bpp_catalog_has_agents(self, http):
        r = http.get(f"{BPP_URL}/api/catalog")
        assert r.status_code == 200
        catalog = r.json()
        assert "resources" in catalog
        assert len(catalog["resources"]) >= 3

    def test_bpp_catalog_agents_have_pricing(self, http):
        r = http.get(f"{BPP_URL}/api/catalog")
        for agent in r.json()["resources"]:
            attrs = agent.get("resourceAttributes", {})
            assert "pricing" in attrs, f"Agent {agent['id']} missing pricing"
            assert attrs["pricing"]["unitPrice"] > 0

    def test_bpp_catalog_agents_have_json_ld_context(self, http):
        r = http.get(f"{BPP_URL}/api/catalog")
        for agent in r.json()["resources"]:
            attrs = agent.get("resourceAttributes", {})
            assert "@context" in attrs, f"Agent {agent['id']} missing @context"
            assert "@type" in attrs, f"Agent {agent['id']} missing @type"


class TestSelectFlow:
    def test_select_returns_transaction_id(self, http):
        r = http.post(f"{BAP_URL}/api/contracts/select", json={
            "agent_id": "agent-summarizer-001",
            "offer_id": "offer-summarizer-basic",
        })
        assert r.status_code == 200
        assert "transactionId" in r.json()

    def test_select_triggers_on_select_callback(self, http):
        r = http.post(f"{BAP_URL}/api/contracts/select", json={})
        txn_id = r.json()["transactionId"]

        time.sleep(2)

        r2 = http.get(f"{BAP_URL}/api/transactions/{txn_id}")
        assert r2.status_code == 200
        txn = r2.json()
        assert "on_select" in txn.get("callbacks", [])


class TestFullFlow:
    def test_select_init_confirm_status_completes(self, http):
        """Full happy path: from select to COMPLETED execution."""
        # 1. Select
        r = http.post(f"{BAP_URL}/api/contracts/select", json={
            "agent_id": "agent-code-reviewer-001",
            "offer_id": "offer-code-review-basic",
        })
        assert r.status_code == 200
        txn_id = r.json()["transactionId"]

        time.sleep(2)  # wait for on_select

        # 2. Init
        r = http.post(f"{BAP_URL}/api/contracts/init", json={"transaction_id": txn_id})
        assert r.status_code == 200

        time.sleep(2)  # wait for on_init

        # 3. Confirm
        r = http.post(f"{BAP_URL}/api/contracts/confirm", json={"transaction_id": txn_id})
        assert r.status_code == 200

        time.sleep(3)  # wait for agent execution + on_confirm

        # 4. Status — poll up to 30s for COMPLETED
        status = None
        for _ in range(15):
            r = http.post(f"{BAP_URL}/api/contracts/status", json={"transaction_id": txn_id})
            assert r.status_code == 200
            time.sleep(2)
            r2 = http.get(f"{BAP_URL}/api/transactions/{txn_id}")
            txn = r2.json()
            if "on_status" in txn.get("callbacks", []):
                perf = txn.get("contract", {}).get("performance", [])
                if perf and perf[0].get("performanceAttributes", {}).get("status") == "COMPLETED":
                    status = "COMPLETED"
                    break

        assert status == "COMPLETED", f"Flow did not complete. Transaction state: {txn}"

    def test_completed_execution_has_performance_attributes(self, http):
        """on_status must include @context, @type, tokensUsed, latencyMs."""
        r = http.post(f"{BAP_URL}/api/contracts/select", json={})
        txn_id = r.json()["transactionId"]
        time.sleep(2)

        http.post(f"{BAP_URL}/api/contracts/init", json={"transaction_id": txn_id})
        time.sleep(2)
        http.post(f"{BAP_URL}/api/contracts/confirm", json={"transaction_id": txn_id})

        for _ in range(15):
            time.sleep(2)
            http.post(f"{BAP_URL}/api/contracts/status", json={"transaction_id": txn_id})
            txn = http.get(f"{BAP_URL}/api/transactions/{txn_id}").json()
            perf = txn.get("contract", {}).get("performance", [])
            if perf:
                attrs = perf[0].get("performanceAttributes", {})
                if attrs.get("status") == "COMPLETED":
                    assert "@context" in attrs
                    assert "@type" in attrs
                    assert "tokensUsed" in attrs
                    assert attrs["tokensUsed"]["total"] > 0
                    assert "latencyMs" in attrs
                    return

        pytest.fail("Execution never completed within 30 seconds")
