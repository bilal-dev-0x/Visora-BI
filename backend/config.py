"""
Centralized configuration for VISORA BI.

This is the single place that reads environment variables / Streamlit
secrets. Nothing else in the codebase should call os.environ or
st.secrets directly for these settings -- that keeps every
configurable value (upload limits, AI context threshold, provider
credentials/models) declared in one spot instead of scattered across
modules.

Nothing here performs any analysis or AI calls -- it only loads and
exposes configuration.
"""

import os
from dataclasses import dataclass
from typing import Optional

try:
    # Optional: if python-dotenv is installed, load a local .env file
    # (already gitignored) so developers can configure providers
    # without exporting shell variables. Silently a no-op otherwise --
    # env vars / Streamlit secrets still work without it.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - optional dependency
    pass


def _get_setting(key, default=None):
    """Look up a configuration value by key.

    Checks, in order:
      1. Environment variables (os.environ / .env) -- works everywhere,
         including local development and non-Streamlit entry points
         (scripts/cli_report.py, tests).
      2. Streamlit secrets (st.secrets), when running under Streamlit
         and a secrets.toml is present -- this is the standard way to
         configure secrets on Streamlit Community Cloud.

    Never raises just because a key is absent from one source; a
    missing key simply falls through to `default`.
    """
    value = os.environ.get(key)
    if value is not None and value != "":
        return value

    try:
        import streamlit as st

        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # No Streamlit runtime, no secrets.toml, or st.secrets access
        # outside of a running app -- all expected, not an error.
        pass

    return default


def _get_int_setting(key, default):
    raw = _get_setting(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Upload / AI-context size policy
#
# Two distinct limits (see backend/upload_policy.py and
# backend/ai_service.py for where each is enforced):
#   * MAX_UPLOAD_SIZE_MB    -- hard cap on what VISORA will ingest at all.
#   * AI_CONTEXT_LIMIT_MB   -- below this, the full analytical JSON may
#                              be sent to the AI provider chain; above
#                              it (but still under the upload cap),
#                              VISORA uses its local analytical results
#                              directly instead.
# Both are plain, named constants (not merged into one limit) so a
# future upgrade can change either independently.
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE_MB = _get_int_setting("VISORA_MAX_UPLOAD_MB", 150)
AI_CONTEXT_LIMIT_MB = _get_int_setting("VISORA_AI_CONTEXT_LIMIT_MB", 100)

MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
AI_CONTEXT_LIMIT_BYTES = AI_CONTEXT_LIMIT_MB * 1024 * 1024

# Formats VISORA officially ingests this milestone: CSV plus Excel
# workbooks (.xlsx/.xlsm, read via openpyxl). JSON/Parquet/PDF/image
# ingestion remains explicitly out of scope for this milestone.
SUPPORTED_UPLOAD_EXTENSIONS = ("csv", "xlsx", "xlsm")

# Network timeout for a single AI provider call, in seconds. A slow
# provider should not hang the dashboard indefinitely -- this is what
# turns an unresponsive provider into a timeout failure that the chain
# can fall through from.
AI_PROVIDER_TIMEOUT_SECONDS = _get_int_setting("VISORA_AI_TIMEOUT_SECONDS", 30)


@dataclass
class ProviderConfig:
    """Configuration for one slot in the AI provider chain.

    `kind` selects which AIProvider implementation to build
    (backend/ai_providers.py): "openai_compatible" for any provider
    that speaks the OpenAI chat-completions REST API (OpenAI, Groq,
    OpenRouter, Together, Fireworks, DeepSeek, Mistral, a local Ollama
    server, ...), or "anthropic" for Anthropic's native Messages API.

    A provider with no api_key is simply unconfigured -- the chain
    skips it rather than attempting (and failing) a call.
    """

    slot: str
    kind: str
    api_key: Optional[str]
    model: Optional[str]
    base_url: Optional[str]
    label: Optional[str] = None

    @property
    def is_configured(self):
        return bool(self.api_key) and bool(self.model)

    @property
    def display_name(self):
        return self.label or f"{self.kind} ({self.model})" if self.model else self.kind


_DEFAULT_BASE_URLS = {
    "openai_compatible": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "nemotron": "https://integrate.api.nvidia.com/v1",
}


def _load_provider(slot_number):
    prefix = f"PROVIDER_{slot_number}_"
    kind = (_get_setting(prefix + "TYPE", "openai_compatible") or "openai_compatible").strip().lower()
    api_key = _get_setting(prefix + "API_KEY")
    model = _get_setting(prefix + "MODEL")
    base_url = _get_setting(prefix + "BASE_URL", _DEFAULT_BASE_URLS.get(kind))
    label = _get_setting(prefix + "LABEL")

    return ProviderConfig(
        slot=f"provider_{slot_number}",
        kind=kind,
        api_key=api_key,
        model=model,
        base_url=base_url,
        label=label,
    )


def load_provider_chain(count=3):
    """Return the list of configured provider slots, in fallback order.

    Slots with no API key/model set are included (callers can see they
    exist) but report `is_configured is False`; backend/ai_service.py
    is responsible for skipping those without attempting a call.
    """
    return [_load_provider(number) for number in range(1, count + 1)]
