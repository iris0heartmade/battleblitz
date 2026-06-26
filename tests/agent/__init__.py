"""
Smoke tests for the LLM agent module.

These tests don't hit the network or the real LLM. They verify:
- All modules import cleanly
- Pydantic schemas validate / reject the right things
- The action-id validation layer catches the common LLM failure modes
- The fallback path activates when the LLM keeps producing garbage

For real LLM tests see test_llm_smoke.py (requires GPU/API + VCR cassettes).
"""
