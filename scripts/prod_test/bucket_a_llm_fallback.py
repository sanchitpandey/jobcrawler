"""Section 4.3 — LLM provider fallback. Direct test of LLMService rotation.

Avoids pytest collection overhead by running the assertions inline.
"""
from __future__ import annotations
import asyncio
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-must-be-32-plus-characters-long-1")
os.environ["FAKE_A_KEY"] = "stub-a"
os.environ["FAKE_B_KEY"] = "stub-b"

sys.path.insert(0, ".")
from api.services.llm import LLMService, Provider  # noqa: E402


class FakeClient:
    def __init__(self, base_url: str, call_log: list[str]):
        self.base_url = base_url
        self.call_log = call_log
        self.chat = MagicMock()
        self.chat.completions = MagicMock()

        async def _create(model=None, messages=None, max_tokens=None, temperature=None):
            self.call_log.append(self.base_url)
            if "a" in self.base_url:
                raise Exception("429 Too Many Requests: tokens per day quota exceeded")
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message = MagicMock(content="ok-from-b")
            resp.choices[0].finish_reason = "stop"
            resp.usage = MagicMock(total_tokens=42)
            return resp

        self.chat.completions.create = _create


async def test_rotation_on_daily_quota():
    call_log: list[str] = []

    def _client_property(self):
        return FakeClient(self._providers[self._provider_index].base_url, call_log)

    # Patch the class property
    LLMService.client = property(_client_property)
    try:
        p_a = Provider(name="A", base_url="http://a", api_key_env="FAKE_A_KEY", models=["a-1"])
        p_b = Provider(name="B", base_url="http://b", api_key_env="FAKE_B_KEY", models=["b-1"])
        svc = LLMService([p_a, p_b])
        text, tokens = await svc.chat("hi")
        assert text == "ok-from-b", f"Expected B fallback, got {text!r}"
        assert tokens == 42, tokens
        assert call_log[0] == "http://a", call_log
        assert call_log[-1] == "http://b", call_log
        print(f"[PASS] 4.3a-rotation-on-daily-quota: rotated A → B, calls={call_log}")
    finally:
        # Restore default (won't matter since process exits, but be tidy)
        pass


class FakeAllFail:
    def __init__(self, base_url: str, call_log: list[str]):
        self.base_url = base_url
        self.call_log = call_log
        self.chat = MagicMock()
        self.chat.completions = MagicMock()

        async def _create(**kw):
            self.call_log.append(base_url)
            raise Exception("429 daily quota exceeded")

        self.chat.completions.create = _create


async def test_all_providers_exhausted():
    call_log: list[str] = []

    def _client_property(self):
        return FakeAllFail(self._providers[self._provider_index].base_url, call_log)

    LLMService.client = property(_client_property)
    p_a = Provider(name="A", base_url="http://a", api_key_env="FAKE_A_KEY", models=["a-1"])
    p_b = Provider(name="B", base_url="http://b", api_key_env="FAKE_B_KEY", models=["b-1"])
    svc = LLMService([p_a, p_b])
    try:
        await svc.chat("hi")
        print("[FAIL] 4.3b-all-exhausted: expected RuntimeError, got success")
    except RuntimeError as e:
        msg = str(e).lower()
        if "exhausted" in msg or "all providers" in msg:
            print(f"[PASS] 4.3b-all-exhausted: RuntimeError surfaced cleanly — '{e}'")
        else:
            print(f"[FAIL] 4.3b-all-exhausted: unexpected message '{e}'")


async def main():
    await test_rotation_on_daily_quota()
    await test_all_providers_exhausted()


if __name__ == "__main__":
    asyncio.run(main())
