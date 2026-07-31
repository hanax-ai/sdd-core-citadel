from agents.gatekeeper import AmigoGatekeeper


def test_format_review_prompt_marks_truncation():
    gk = AmigoGatekeeper(api_key="unused")
    prompt = gk.format_review_prompt("task", "x" * 4000)
    assert "[...diff truncated...]" in prompt


def test_format_review_prompt_no_marker_when_short():
    gk = AmigoGatekeeper(api_key="unused")
    prompt = gk.format_review_prompt("task", "short diff")
    assert "[...diff truncated...]" not in prompt
