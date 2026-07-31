import agents.gatekeeper as gatekeeper_module
from agents.gatekeeper import AmigoGatekeeper


def test_review_returns_empty_list_on_pass(monkeypatch):
    monkeypatch.setattr(gatekeeper_module, "call_gatekeeper", lambda system, user: "PASS")
    findings = AmigoGatekeeper(api_key="unused").review("diff text", {"git_status": {}})
    assert findings == []


def test_review_returns_findings_list_when_not_passing(monkeypatch):
    monkeypatch.setattr(
        gatekeeper_module,
        "call_gatekeeper",
        lambda system, user: "Missing test coverage\nUnused import",
    )
    findings = AmigoGatekeeper(api_key="unused").review("diff text", {"git_status": {}})
    assert findings == ["Missing test coverage", "Unused import"]
