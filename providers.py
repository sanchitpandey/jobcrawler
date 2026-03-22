"""
providers.py
────────────
Single place that manages ALL free LLM providers.
Every other file (score.py, form_filler.py, cover.py) imports from here.

Usage:
    from providers import get_client, chat

    response = chat("your prompt here")   # uses whatever provider is active

To switch provider, just set env var before running:
    $env:LLM_PROVIDER = "openrouter"     # Windows
    export LLM_PROVIDER=openrouter        # Linux/Mac

Or pass inline:
    python main.py  (uses GROQ by default if GROQ_API_KEY is set)

──────────────────────────────────────────────────────────────────
PROVIDER COMPARISON (as of March 2026):
──────────────────────────────────────────────────────────────────
Provider      Model                           Free Limits         CC?  Setup
──────────────────────────────────────────────────────────────────
groq          llama-3.3-70b-versatile         100K tok/day        No   GROQ_API_KEY
openrouter    meta-llama/llama-3.3-70b:free   200 req/day        No   OPENROUTER_API_KEY
openrouter    google/gemini-2.0-flash-exp:free 200 req/day       No   same key, diff model
openrouter    deepseek/deepseek-r1:free        200 req/day        No   same key, diff model
openrouter    mistralai/mistral-small:free     200 req/day        No   same key, diff model
cerebras      llama-3.3-70b                   60 req/min free     No   CEREBRAS_API_KEY
──────────────────────────────────────────────────────────────────

STRATEGY while debugging (rotating to avoid hitting limits):
  - Set LLM_PROVIDER=openrouter and OPENROUTER_API_KEY
  - The provider cycles through 4 free OpenRouter models
  - Each model has its OWN 200 req/day quota
  - Combined: 800 req/day = ~800 job batches = thousands of jobs
  - If one model's daily limit is hit, auto-falls to the next model

──────────────────────────────────────────────────────────────────
QUICK SETUP (pick one):

  GROQ (best quality, 100K tok/day):
    $env:GROQ_API_KEY = "gsk_..."
    python main.py

  OPENROUTER (best for debugging, 800 req/day stacked):
    $env:OPENROUTER_API_KEY = "sk-or-..."
    $env:LLM_PROVIDER = "openrouter"
    python main.py

  CEREBRAS (fastest responses, generous free tier):
    $env:CEREBRAS_API_KEY = "csk-..."
    $env:LLM_PROVIDER = "cerebras"
    python main.py

  AUTO (tries Groq → OpenRouter → Cerebras, uses whatever key you have):
    $env:LLM_PROVIDER = "auto"
    python main.py
──────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import os
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger("crawler.providers")


# ── Provider definitions ───────────────────────────────────────────────────────
@dataclass
class Provider:
    name:        str
    base_url:    str
    api_key_env: str
    models:      list[str]          # in priority order; rotate on 429
    max_tokens:  int  = 900
    extra_headers: dict = field(default_factory=dict)

    @property
    def api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env)

    @property
    def available(self) -> bool:
        return bool(self.api_key)


PROVIDERS: dict[str, Provider] = {

    "groq": Provider(
        name        = "Groq",
        base_url    = "https://api.groq.com/openai/v1",
        api_key_env = "GROQ_API_KEY",
        models      = [
            "llama-3.3-70b-versatile",   # 100K tok/day — best quality
            "llama-3.1-8b-instant",       # separate quota, fires when 70b is exhausted
            "gemma2-9b-it",               # third separate quota
        ],
    ),

    "openrouter": Provider(
        name        = "OpenRouter",
        base_url    = "https://openrouter.ai/api/v1",
        api_key_env = "OPENROUTER_API_KEY",
        # Each :free model has its OWN 200 req/day quota — stacked = ~800/day
        models      = [
            "meta-llama/llama-3.3-70b-instruct:free",         # proven, reliable JSON
            "mistralai/mistral-small-3.1-24b-instruct:free",  # fast fallback
            "google/gemma-3-27b-it:free",                     # last resort
        ],
        extra_headers = {
            "HTTP-Referer": "https://github.com/jobcrawler",
            "X-Title":      "JobCrawler",
        },
    ),

    "cerebras": Provider(
        name        = "Cerebras",
        base_url    = "https://api.cerebras.ai/v1",
        api_key_env = "CEREBRAS_API_KEY",
        models      = [
            "llama-3.3-70b",
            "llama-3.1-8b",
        ],
    ),

    "together": Provider(
        name        = "Together AI",
        base_url    = "https://api.together.xyz/v1",
        api_key_env = "TOGETHER_API_KEY",
        models      = [
            "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        ],
    ),
}


# ── Active session ─────────────────────────────────────────────────────────────
class LLMSession:
    """
    Single session that wraps one provider and rotates models on 429.
    Automatically falls back to the next model in the list when one is exhausted.
    """

    def __init__(self, provider: Provider):
        self.provider     = provider
        self.model_index  = 0
        self._client: Optional[OpenAI] = None
        log.info("LLM session: provider=%s model=%s",
                 provider.name, self.current_model)

    @property
    def current_model(self) -> str:
        return self.provider.models[self.model_index]

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key  = self.provider.api_key,
                base_url = self.provider.base_url,
                default_headers = self.provider.extra_headers,
            )
        return self._client

    def _next_model(self) -> bool:
        """Rotate to the next model. Returns False if no more models."""
        if self.model_index + 1 < len(self.provider.models):
            self.model_index += 1
            log.warning("Rotating to next model: %s", self.current_model)
            return True
        return False

    def _parse_wait(self, error_str: str) -> float:
        """Extract actual wait time from rate limit error message."""
        m = re.search(
            r"try again in\s+(?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)s",
            error_str, re.IGNORECASE
        )
        if m:
            h = int(m.group(1) or 0)
            mn = int(m.group(2) or 0)
            s = float(m.group(3) or 0)
            return min(h * 3600 + mn * 60 + s + 5, 1800)

        # Check retry-after header value embedded in error string
        ra = re.search(r"retry.after[\":\s]+(\d+)", error_str, re.IGNORECASE)
        if ra:
            return int(ra.group(1)) + 5

        return 65  # safe default

    def chat(
        self,
        prompt:     str,
        max_tokens: int = 900,
        temperature: float = 0.1,
    ) -> str:
        """
        Call the LLM. Auto-rotates models on rate limit.
        Raises RuntimeError only if ALL models are exhausted.
        """
        for attempt in range(6):
            try:
                resp = self.client.chat.completions.create(
                    model       = self.current_model,
                    messages    = [{"role": "user", "content": prompt}],
                    max_tokens  = max_tokens,
                    temperature = temperature,
                )
                text = resp.choices[0].message.content
                if text:
                    log.debug("LLM response (%s, %d chars)", self.current_model, len(text))
                    return text.strip()
                raise ValueError("Empty response from model")

            except Exception as e:
                err = str(e)
                is_rate_limit = (
                    "429" in err or
                    "rate_limit" in err.lower() or
                    "too many requests" in err.lower()
                )
                is_daily_limit = any(x in err.lower() for x in [
                    "tokens per day", "tpd", "daily", "quota"
                ])

                if is_rate_limit:
                    if is_daily_limit:
                        log.warning(
                            "Model %s daily limit exhausted. Rotating...",
                            self.current_model
                        )
                        if not self._next_model():
                            raise RuntimeError(
                                f"All {self.provider.name} models exhausted for today. "
                                f"Switch provider: set LLM_PROVIDER=openrouter"
                            ) from e
                        continue  # retry immediately with new model

                    # TPM rate limit — wait the real retry-after time
                    wait = self._parse_wait(err)
                    log.warning(
                        "Rate limit on %s (attempt %d) — waiting %.0fs",
                        self.current_model, attempt + 1, wait
                    )
                    time.sleep(wait)
                    continue

                # Non-rate-limit error — retry with backoff
                if attempt < 3:
                    backoff = 5 * (attempt + 1)
                    log.warning("Error on %s (attempt %d): %s — retrying in %ds",
                                self.current_model, attempt + 1, err[:120], backoff)
                    time.sleep(backoff)
                else:
                    raise RuntimeError(
                        f"LLM call failed after {attempt+1} attempts: {err[:200]}"
                    ) from e

        raise RuntimeError("LLM call exhausted all retry attempts")


# ── Module-level session singleton ─────────────────────────────────────────────
_session: Optional[LLMSession] = None


def get_session() -> LLMSession:
    """
    Get or create the active LLM session.
    Provider is selected by LLM_PROVIDER env var (default: auto-detect from keys).
    """
    global _session
    if _session is not None:
        return _session

    desired = os.environ.get("LLM_PROVIDER", "auto").lower()

    if desired == "auto":
        # Try providers in preference order based on what keys are set
        order = ["groq", "openrouter", "cerebras", "together"]
        for name in order:
            p = PROVIDERS[name]
            if p.available:
                log.info("AUTO: selected provider=%s (key found)", p.name)
                _session = LLMSession(p)
                return _session
        raise EnvironmentError(
            "No LLM API key found. Set one of:\n"
            "  GROQ_API_KEY       → get free key at console.groq.com\n"
            "  OPENROUTER_API_KEY → get free key at openrouter.ai\n"
            "  CEREBRAS_API_KEY   → get free key at inference.cerebras.ai\n"
        )

    if desired not in PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{desired}'. "
            f"Valid: {list(PROVIDERS.keys())} or 'auto'"
        )

    provider = PROVIDERS[desired]
    if not provider.available:
        raise EnvironmentError(
            f"LLM_PROVIDER={desired} but {provider.api_key_env} is not set.\n"
            f"Set it: $env:{provider.api_key_env} = 'your-key'"
        )

    log.info("Using provider: %s | model: %s", provider.name, provider.models[0])
    _session = LLMSession(provider)
    return _session


def chat(prompt: str, max_tokens: int = 900, temperature: float = 0.1) -> str:
    """Convenience function — just call this from anywhere."""
    return get_session().chat(prompt, max_tokens=max_tokens, temperature=temperature)


def reset_session():
    """Force a new session (useful for testing)."""
    global _session
    _session = None