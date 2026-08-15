"""
These tests hit a real local Ollama + Qdrant instance, so they're integration
tests -- run `docker compose up -d qdrant`, `ollama serve`, and
`python -m app.rag.build_index` before running pytest.
"""
import pytest
from app.agent.graph import agent_graph


@pytest.mark.integration
def test_menu_question_en():
    config = {"configurable": {"thread_id": "test-en"}}
    result = agent_graph.invoke(
        {"user_id": "test-en", "user_message": "What is the price of Kacchi Biryani?"},
        config=config,
    )
    assert result["language"] == "en"
    assert "380" in result["response"]


@pytest.mark.integration
def test_menu_question_bn():
    config = {"configurable": {"thread_id": "test-bn"}}
    result = agent_graph.invoke(
        {"user_id": "test-bn", "user_message": "কাচ্চি বিরিয়ানির দাম কত?"},
        config=config,
    )
    assert result["language"] == "bn"
