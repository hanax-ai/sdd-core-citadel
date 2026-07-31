import agents.gatekeeper as gatekeeper_module
from agents.gatekeeper import AmigoGatekeeper, has_blocking_findings


async def test_review_returns_structured_findings(monkeypatch):
    async def fake_call_gatekeeper(system, user):
        return {
            "text": "{}",
            "findings": [{"line": 5, "severity": "NOTE", "text": "pre-existing, out of scope"}],
            "input_tokens": 1,
            "output_tokens": 1,
            "elapsed_ms": 1,
        }

    monkeypatch.setattr(gatekeeper_module, "call_gatekeeper", fake_call_gatekeeper)
    findings = await AmigoGatekeeper(api_key="unused").review("diff text", {"git_status": {}})
    assert findings == [{"line": 5, "severity": "NOTE", "text": "pre-existing, out of scope"}]


async def test_review_returns_empty_list_when_no_findings(monkeypatch):
    async def fake_call_gatekeeper(system, user):
        return {"text": "{}", "findings": [], "input_tokens": 1, "output_tokens": 1, "elapsed_ms": 1}

    monkeypatch.setattr(gatekeeper_module, "call_gatekeeper", fake_call_gatekeeper)
    findings = await AmigoGatekeeper(api_key="unused").review("diff text", {"git_status": {}})
    assert findings == []


def test_has_blocking_findings_true_for_critical():
    assert has_blocking_findings([{"line": 1, "severity": "CRITICAL", "text": "x"}]) is True


def test_has_blocking_findings_true_for_warning():
    assert has_blocking_findings([{"line": 1, "severity": "WARNING", "text": "x"}]) is True


def test_has_blocking_findings_false_for_note_only():
    assert has_blocking_findings([{"line": 1, "severity": "NOTE", "text": "x"}]) is False


def test_has_blocking_findings_false_for_empty():
    assert has_blocking_findings([]) is False
