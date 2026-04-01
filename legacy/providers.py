"""LLM provider management for scoring and cover letter generation."""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

try:
    import google.auth
    import google.auth.transport.requests
    _GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    _GOOGLE_AUTH_AVAILABLE = False

load_dotenv()
log = logging.getLogger("crawler.providers")


@dataclass
class Provider:
    name: str
    base_url: str
    api_key_env: str
    models: list[str]
    max_tokens: int = 900
    extra_headers: dict[str, str] = field(default_factory=dict)

    @property
    def api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env)

    @property
    def available(self) -> bool:
        return bool(self.api_key)


class VertexAIProvider(Provider):
    """Provider that uses Google OAuth instead of a static API key."""

    def __init__(self):
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        super().__init__(
            name="Vertex AI",
            base_url=(
                f"https://{location}-aiplatform.googleapis.com/v1beta1"
                f"/projects/{project}/locations/{location}/endpoints/openapi"
            ),
            api_key_env="GOOGLE_CLOUD_PROJECT",
            models=["google/gemini-2.5-flash-lite"],
        )
        self._project = project
        self._credentials = None

    @property
    def available(self) -> bool:
        return bool(self._project) and _GOOGLE_AUTH_AVAILABLE

    @property
    def api_key(self) -> Optional[str]:
        """Returns a fresh OAuth access token."""
        if self._credentials is None:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        self._credentials.refresh(google.auth.transport.requests.Request())
        return self._credentials.token


PROVIDER_ORDER = ["vertex_ai", "groq", "openrouter", "cerebras", "together"]

PROVIDERS: dict[str, Provider] = {
    "groq": Provider(
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        models=["llama-3.3-70b-versatile"],
    ),
    "openrouter": Provider(
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        models=[
            "google/gemini-2.5-flash-lite",
            "meta-llama/llama-3.3-70b-instruct:free",
            "mistralai/mistral-small-3.1-24b-instruct:free",
            "google/gemma-3-27b-it:free",
        ],
        extra_headers={
            "HTTP-Referer": "https://github.com/jobcrawler",
            "X-Title": "JobCrawler",
        },
    ),
    "cerebras": Provider(
        name="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        models=["llama-3.3-70b", "llama-3.1-8b"],
    ),
    "together": Provider(
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        models=["meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"],
    ),
}


class LLMSession:
    def __init__(self, providers: list[Provider]):
        self._providers = providers
        self._provider_index = 0
        self._client: Optional[OpenAI] = None
        log.info("LLM session: provider=%s model=%s", self.provider.name, self.current_model)

    @property
    def provider(self) -> Provider:
        return self._providers[self._provider_index]

    @property
    def current_model(self) -> str:
        return self.provider.models[0]

    @property
    def client(self) -> OpenAI:
        # VertexAIProvider returns a short-lived OAuth token — rebuild client each call
        if isinstance(self.provider, VertexAIProvider) or self._client is None:
            self._client = OpenAI(
                api_key=self.provider.api_key,
                base_url=self.provider.base_url,
                default_headers=self.provider.extra_headers,
            )
        return self._client

    def _rotate_provider(self) -> bool:
        exhausted = self._providers[self._provider_index].name
        if self._provider_index + 1 < len(self._providers):
            self._provider_index += 1
            self._client = None  # new provider needs new client
            log.warning(
                "Daily limit on %s. Rotating to provider: %s / %s",
                exhausted, self.provider.name, self.current_model,
            )
            return True
        return False

    def _parse_wait(self, error_str: str) -> float:
        match = re.search(r"try again in\s+(?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = float(match.group(3) or 0)
            return min(hours * 3600 + minutes * 60 + seconds + 5, 1800)

        retry_after = re.search(r"retry.after[\":\s]+(\d+)", error_str, re.IGNORECASE)
        if retry_after:
            return int(retry_after.group(1)) + 5
        return 65

    def chat(self, prompt: str, max_tokens: int = 900, temperature: float = 0.1) -> str:
        for attempt in range(6):
            try:
                response = self.client.chat.completions.create(
                    model=self.current_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                choice = response.choices[0]
                if choice.message is None:
                    reason = getattr(choice, "finish_reason", "unknown")
                    raise ValueError(f"Null message from model (finish_reason={reason})")
                text = choice.message.content
                if text:
                    return text.strip()
                raise ValueError("Empty response from model")
            except Exception as exc:
                error = str(exc)
                is_rate_limit = "429" in error or "rate_limit" in error.lower() or "too many requests" in error.lower()
                is_daily_limit = any(token in error.lower() for token in ["tokens per day", "tpd", "daily", "quota"])

                if is_rate_limit:
                    if is_daily_limit:
                        log.warning("Model %s daily limit exhausted. Rotating provider.", self.current_model)
                        if not self._rotate_provider():
                            raise RuntimeError("All providers are exhausted for today.") from exc
                        continue

                    wait = self._parse_wait(error)
                    log.warning("Rate limit on %s (attempt %d). Waiting %.0fs", self.current_model, attempt + 1, wait)
                    time.sleep(wait)
                    continue

                if attempt < 3:
                    backoff = 5 * (attempt + 1)
                    log.warning("Error on %s (attempt %d): %s. Retrying in %ds", self.current_model, attempt + 1, error[:120], backoff)
                    time.sleep(backoff)
                else:
                    raise RuntimeError(f"LLM call failed after {attempt + 1} attempts: {error[:200]}") from exc

        raise RuntimeError("LLM call exhausted all retry attempts")


_session: Optional[LLMSession] = None


def _make_provider(name: str) -> Provider:
    if name == "vertex_ai":
        return VertexAIProvider()
    return PROVIDERS[name]


def get_session() -> LLMSession:
    global _session
    if _session is not None:
        return _session

    desired = os.environ.get("LLM_PROVIDER", "auto").lower()
    if desired == "auto":
        ordered = [p for name in PROVIDER_ORDER if (p := _make_provider(name)).available]
        if not ordered:
            raise EnvironmentError(
                "No LLM provider available. Set one of: GOOGLE_CLOUD_PROJECT (Vertex AI), "
                "GROQ_API_KEY, OPENROUTER_API_KEY, CEREBRAS_API_KEY, or TOGETHER_API_KEY."
            )
        log.info(
            "AUTO selected %d provider(s): %s",
            len(ordered),
            " -> ".join(f"{p.name}/{p.models[0]}" for p in ordered),
        )
        _session = LLMSession(ordered)
        return _session

    if desired == "vertex_ai":
        provider = VertexAIProvider()
        if not provider.available:
            raise EnvironmentError("LLM_PROVIDER=vertex_ai but GOOGLE_CLOUD_PROJECT is not set.")
    elif desired not in PROVIDERS:
        raise ValueError(f"Unknown LLM_PROVIDER='{desired}'. Valid options: vertex_ai, {list(PROVIDERS)}, or 'auto'.")
    else:
        provider = PROVIDERS[desired]
        if not provider.available:
            raise EnvironmentError(f"LLM_PROVIDER={desired} but {provider.api_key_env} is not set.")

    log.info("Using provider: %s | model: %s", provider.name, provider.models[0])
    _session = LLMSession([provider])
    return _session


def chat(prompt: str, max_tokens: int = 900, temperature: float = 0.1) -> str:
    return get_session().chat(prompt, max_tokens=max_tokens, temperature=temperature)


def reset_session() -> None:
    global _session
    _session = None
