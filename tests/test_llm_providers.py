"""LLM remediation: OpenAI-compatible path without real network."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from auto_research.agent_loop import _llm_remediation


@patch("auto_research.agent_loop.httpx.Client")
def test_llm_remediation_openai_when_no_anthropic(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "## suggestion"}}]}
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client_cls.return_value.__exit__.return_value = None

    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ["OPENAI_API_KEY"] = "sk-test"
    os.environ.pop("AUTO_RESEARCH_LLM_PROVIDER", None)
    try:
        out = _llm_remediation(
            "name: t\ncommand: []\nmetrics_path: metrics.json\n",
            {"thresholds_passed": True},
            {"summary": {}, "metrics": {}},
        )
        assert out == "## suggestion"
        mock_client.post.assert_called_once()
    finally:
        os.environ.pop("OPENAI_API_KEY", None)
