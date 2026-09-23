"""
AI provider abstraction (Day 3).

Each provider exposes one method -- complete(system, prompt) -> str --
so backend/ai_service.py's fallback chain never has to know which
vendor it is talking to. A provider never crashes the caller: every
failure mode (timeout, auth, quota/rate-limit, network, malformed
response, or anything else) is raised as an AIProviderError carrying a
short, sanitized `category` and `message` that is safe to show in the
UI (never the raw response body, headers, or API key).

This module performs no analytical calculation and no business-metric
interpretation of its own -- it only transports a prompt that
backend/ai_service.py already built from VISORA's analytical context,
and returns the provider's text response.
"""

import json
import urllib.parse

import requests

from backend.config import AI_PROVIDER_TIMEOUT_SECONDS


class AIProviderError(Exception):
    """Raised by any provider call that did not produce usable text.

    category is one of: "not_configured", "timeout", "auth", "quota",
    "network", "unavailable", "invalid_response".
    """

    def __init__(self, provider_name, category, message):
        self.provider_name = provider_name
        self.category = category
        self.message = message
        super().__init__(f"[{provider_name}] {category}: {message}")


class AIProvider:
    """Base interface every concrete provider implements."""

    def __init__(self, config):
        self.config = config

    @property
    def name(self):
        return self.config.display_name

    def complete(self, system, prompt):
        """Return the provider's text response, or raise AIProviderError."""
        raise NotImplementedError


class OpenAICompatibleProvider(AIProvider):
    """Works with any provider that speaks the OpenAI chat-completions
    REST API (OpenAI, Groq, OpenRouter, Together, Fireworks, DeepSeek,
    Mistral, a local Ollama server, etc.) -- the endpoint shape is the
    same, only base_url/api_key/model differ, which is exactly what
    ProviderConfig captures."""

    def complete(self, system, prompt):
        if not self.config.is_configured:
            raise AIProviderError(self.name, "not_configured", "No API key/model configured for this slot.")

        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        response = self._send(url, headers, payload)
        return self._extract_text(response)

    def _send(self, url, headers, payload):
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=AI_PROVIDER_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout as exc:
            raise AIProviderError(self.name, "timeout", "Request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise AIProviderError(self.name, "network", "Could not reach the provider.") from exc
        except requests.exceptions.RequestException as exc:
            raise AIProviderError(self.name, "network", f"Request failed: {exc.__class__.__name__}") from exc

        if response.status_code in (401, 403):
            raise AIProviderError(self.name, "auth", "Authentication failed (check the API key).")
        if response.status_code == 429:
            raise AIProviderError(self.name, "quota", "Rate limit or quota exceeded.")
        if response.status_code >= 500:
            raise AIProviderError(self.name, "unavailable", f"Provider returned {response.status_code}.")
        if response.status_code >= 400:
            raise AIProviderError(self.name, "unavailable", f"Provider rejected the request ({response.status_code}).")

        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError(self.name, "invalid_response", "Response was not valid JSON.") from exc

    def _extract_text(self, data):
        try:
            choices = data["choices"]
            text = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(self.name, "invalid_response", "Response did not contain expected content.") from exc

        if not isinstance(text, str) or not text.strip():
            raise AIProviderError(self.name, "invalid_response", "Response text was empty.")
        return text.strip()


class AnthropicProvider(AIProvider):
    """Anthropic's native Messages API (api.anthropic.com/v1/messages),
    which uses a different auth header and request/response shape than
    the OpenAI-compatible providers above."""

    _API_VERSION = "2023-06-01"

    def complete(self, system, prompt):
        if not self.config.is_configured:
            raise AIProviderError(self.name, "not_configured", "No API key/model configured for this slot.")

        url = f"{self.config.base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self._API_VERSION,
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "max_tokens": 1000,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = self._send(url, headers, payload)
        return self._extract_text(response)

    def _send(self, url, headers, payload):
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=AI_PROVIDER_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout as exc:
            raise AIProviderError(self.name, "timeout", "Request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise AIProviderError(self.name, "network", "Could not reach the provider.") from exc
        except requests.exceptions.RequestException as exc:
            raise AIProviderError(self.name, "network", f"Request failed: {exc.__class__.__name__}") from exc

        if response.status_code in (401, 403):
            raise AIProviderError(self.name, "auth", "Authentication failed (check the API key).")
        if response.status_code == 429:
            raise AIProviderError(self.name, "quota", "Rate limit or quota exceeded.")
        if response.status_code >= 500:
            raise AIProviderError(self.name, "unavailable", f"Provider returned {response.status_code}.")
        if response.status_code >= 400:
            raise AIProviderError(self.name, "unavailable", f"Provider rejected the request ({response.status_code}).")

        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError(self.name, "invalid_response", "Response was not valid JSON.") from exc

    def _extract_text(self, data):
        try:
            blocks = data["content"]
            text = "".join(block["text"] for block in blocks if block.get("type") == "text")
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(self.name, "invalid_response", "Response did not contain expected content.") from exc

        if not text.strip():
            raise AIProviderError(self.name, "invalid_response", "Response text was empty.")
        return text.strip()


class GeminiProvider(AIProvider):
    """Google Gemini API (generativelanguage.googleapis.com).

    Uses the native Gemini REST API which differs from OpenAI-compatible
    APIs: API key passed as query parameter, different request/response
    format with 'contents' array and 'candidates' in response.
    """

    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def complete(self, system, prompt):
        if not self.config.is_configured:
            raise AIProviderError(self.name, "not_configured", "No API key/model configured for this slot.")

        # Combine system + prompt into a single user message for Gemini
        # (Gemini doesn't have a separate system role in the same way)
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        base_url = (self.config.base_url or self._BASE_URL).rstrip("/")
        url = f"{base_url}/models/{self.config.model}:generateContent?key={self.config.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }

        response = self._send(url, headers, payload)
        return self._extract_text(response)

    def _send(self, url, headers, payload):
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=AI_PROVIDER_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout as exc:
            raise AIProviderError(self.name, "timeout", "Request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise AIProviderError(self.name, "network", "Could not reach the provider.") from exc
        except requests.exceptions.RequestException as exc:
            raise AIProviderError(self.name, "network", f"Request failed: {exc.__class__.__name__}") from exc

        if response.status_code in (401, 403):
            raise AIProviderError(self.name, "auth", "Authentication failed (check the API key).")
        if response.status_code == 429:
            raise AIProviderError(self.name, "quota", "Rate limit or quota exceeded.")
        if response.status_code >= 500:
            raise AIProviderError(self.name, "unavailable", f"Provider returned {response.status_code}.")
        if response.status_code >= 400:
            raise AIProviderError(self.name, "unavailable", f"Provider rejected the request ({response.status_code}).")

        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError(self.name, "invalid_response", "Response was not valid JSON.") from exc

    def _extract_text(self, data):
        try:
            candidates = data["candidates"]
            content = candidates[0]["content"]
            parts = content["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(self.name, "invalid_response", "Response did not contain expected content.") from exc

        if not isinstance(text, str) or not text.strip():
            raise AIProviderError(self.name, "invalid_response", "Response text was empty.")
        return text.strip()


class NemotronProvider(AIProvider):
    """NVIDIA Nemotron via NVIDIA NIM API (integrate.api.nvidia.com).

    NVIDIA's NIM API is OpenAI-compatible, so this provider uses the
    same chat-completions endpoint shape with NVIDIA-specific defaults.
    """

    _DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"

    def complete(self, system, prompt):
        if not self.config.is_configured:
            raise AIProviderError(self.name, "not_configured", "No API key/model configured for this slot.")

        base_url = (self.config.base_url or self._DEFAULT_BASE_URL).rstrip("/")
        if not base_url.endswith("/v1"):
            url = f"{base_url}/v1/chat/completions"
        else:
            url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        response = self._send(url, headers, payload)
        return self._extract_text(response)

    def _send(self, url, headers, payload):
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=AI_PROVIDER_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout as exc:
            raise AIProviderError(self.name, "timeout", "Request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise AIProviderError(self.name, "network", "Could not reach the provider.") from exc
        except requests.exceptions.RequestException as exc:
            raise AIProviderError(self.name, "network", f"Request failed: {exc.__class__.__name__}") from exc

        if response.status_code in (401, 403):
            raise AIProviderError(self.name, "auth", "Authentication failed (check the API key).")
        if response.status_code == 429:
            raise AIProviderError(self.name, "quota", "Rate limit or quota exceeded.")
        if response.status_code >= 500:
            raise AIProviderError(self.name, "unavailable", f"Provider returned {response.status_code}.")
        if response.status_code >= 400:
            raise AIProviderError(self.name, "unavailable", f"Provider rejected the request ({response.status_code}).")

        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError(self.name, "invalid_response", "Response was not valid JSON.") from exc

    def _extract_text(self, data):
        try:
            choices = data["choices"]
            text = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(self.name, "invalid_response", "Response did not contain expected content.") from exc

        if not isinstance(text, str) or not text.strip():
            raise AIProviderError(self.name, "invalid_response", "Response text was empty.")
        return text.strip()


_PROVIDER_CLASSES = {
    "openai_compatible": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "nemotron": NemotronProvider,
}


def build_provider(config):
    """Return an AIProvider instance for a ProviderConfig, or None if
    its `kind` isn't recognized (treated as unconfigured, never a
    crash)."""
    provider_class = _PROVIDER_CLASSES.get(config.kind)
    if provider_class is None:
        return None
    return provider_class(config)
