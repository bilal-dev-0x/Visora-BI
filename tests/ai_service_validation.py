"""Standalone validation for backend/config.py (upload + AI
context size policy, provider config loading), backend/ai_providers.py
(provider abstraction, categorized failures), and backend/ai_service.py
(fallback chain orchestration + local fallback). Mirrors the
pass/fail-list style of the other tests/*_validation.py scripts.

Uses unittest.mock to stand in for the network calls a real provider
would make -- no real API keys or network access required to run this.
"""
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS, FAIL = [], []


def check(name, condition):
    if condition:
        PASS.append(name)
        print(f"PASS: {name}")
    else:
        FAIL.append(name)
        print(f"FAIL: {name}")


def _fake_response(status_code=200, json_data=None, raise_json_error=False):
    response = MagicMock()
    response.status_code = status_code
    if raise_json_error:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = json_data or {}
    return response


def _openai_success_payload(text="AI generated summary."):
    return {"choices": [{"message": {"content": text}}]}


def _anthropic_success_payload(text="AI generated summary."):
    return {"content": [{"type": "text", "text": text}]}


def _gemini_success_payload(text="AI generated summary."):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _nemotron_success_payload(text="AI generated summary."):
    return {"choices": [{"message": {"content": text}}]}


SAMPLE_CONTEXT = {
    "dataset": {"original_filename": "sales.csv"},
    "schema": {"columns": ["Order Date", "Category", "Sales"]},
    "data_quality": {"total_missing_values": 3, "duplicate_rows": 1},
    "metrics": {
        "available": True,
        "data": {"Sales": {"sum": 1000.0, "average": 100.0, "min": 10.0, "max": 400.0, "count": 10}},
    },
    "trends": {
        "available": True,
        "data": {
            "measure_column": "Sales",
            "growth": [
                {"period": "2026-01", "value": 100.0, "growth_percent": None, "growth_reason": "no_previous_period"},
                {"period": "2026-02", "value": 112.5, "growth_percent": 12.5, "growth_reason": None},
            ],
            "period_comparison": {
                "available": True, "reason": None, "previous_period": "2026-01", "current_period": "2026-02",
                "previous_value": 100.0, "current_value": 112.5, "change": 12.5, "change_percent": 8.0,
            },
        },
    },
    "contribution": {
        "available": True,
        "data": {
            "dimension": "Category",
            "measure": "Sales",
            "breakdown": [{"category": "Tech", "value": 600.0, "percent": 60.0, "rank": 1}],
        },
    },
    "anomalies": {"available": True, "data": {"Sales": [{"row_id": 3, "value": 9000}]}},
}

EMPTY_CONTEXT = {
    "dataset": {"original_filename": "empty.csv"},
    "data_quality": {"total_missing_values": 0, "duplicate_rows": 0},
    "metrics": {"available": False, "data": None, "reason": "no numeric columns"},
    "trends": {"available": False, "data": None, "reason": "no date column"},
    "contribution": {"available": False, "data": None, "reason": "no dimension"},
    "anomalies": {"available": False, "data": None, "reason": "no numeric columns"},
}


def with_env(**env_vars):
    """Context manager that sets env vars, reloads backend.config and
    backend.ai_service so they pick up the new values, then restores
    the previous environment and modules afterward."""

    class _Ctx:
        def __enter__(self):
            self._old_env = dict(os.environ)
            for i in (1, 2, 3):
                for suffix in ("TYPE", "API_KEY", "MODEL", "BASE_URL", "LABEL"):
                    os.environ[f"PROVIDER_{i}_{suffix}"] = ""
            for suffix in ("MAX_UPLOAD_MB", "AI_CONTEXT_LIMIT_MB", "AI_TIMEOUT_SECONDS"):
                os.environ[f"VISORA_{suffix}"] = ""
            for key, value in env_vars.items():
                if value is not None:
                    os.environ[key] = str(value)
                else:
                    os.environ[key] = ""
            import backend.config as config_module
            import backend.ai_providers as providers_module
            import backend.ai_service as service_module
            importlib.reload(config_module)
            importlib.reload(providers_module)
            importlib.reload(service_module)
            return service_module

        def __exit__(self, *exc_info):
            os.environ.clear()
            os.environ.update(self._old_env)
            import backend.config as config_module
            import backend.ai_providers as providers_module
            import backend.ai_service as service_module
            importlib.reload(config_module)
            importlib.reload(providers_module)
            importlib.reload(service_module)

    return _Ctx()


def main():
    # ---- Config: defaults and overrides ----
    with with_env(
        VISORA_MAX_UPLOAD_MB=None, VISORA_AI_CONTEXT_LIMIT_MB=None,
        PROVIDER_1_API_KEY=None, PROVIDER_2_API_KEY=None, PROVIDER_3_API_KEY=None,
    ):
        import backend.config as config
        check("Config: default upload limit is 150 MB", config.MAX_UPLOAD_SIZE_MB == 150)
        check("Config: default AI context limit is 100 MB", config.AI_CONTEXT_LIMIT_MB == 100)
        check(
            "Config: upload limit and AI limit are distinct constants",
            config.MAX_UPLOAD_SIZE_BYTES != config.AI_CONTEXT_LIMIT_BYTES,
        )
        chain = config.load_provider_chain()
        check("Config: provider chain has 3 slots", len(chain) == 3)
        check("Config: unconfigured providers report is_configured=False", all(not p.is_configured for p in chain))

    with with_env(VISORA_MAX_UPLOAD_MB="42", VISORA_AI_CONTEXT_LIMIT_MB="17"):
        import backend.config as config
        check("Config: upload limit is overridable via env", config.MAX_UPLOAD_SIZE_MB == 42)
        check("Config: AI context limit is overridable via env", config.AI_CONTEXT_LIMIT_MB == 17)

    with with_env(
        PROVIDER_1_TYPE="openai_compatible", PROVIDER_1_API_KEY="sk-test", PROVIDER_1_MODEL="gpt-test",
        PROVIDER_1_BASE_URL="https://example.invalid/v1",
    ):
        import backend.config as config
        chain = config.load_provider_chain()
        check("Config: configured provider slot reports is_configured=True", chain[0].is_configured)
        check("Config: unconfigured slots stay unconfigured", not chain[1].is_configured and not chain[2].is_configured)

    # ---- Provider chain: sequential fallback ----
    provider_env = {
        "PROVIDER_1_TYPE": "openai_compatible", "PROVIDER_1_API_KEY": "k1", "PROVIDER_1_MODEL": "m1",
        "PROVIDER_1_BASE_URL": "https://p1.invalid/v1",
        "PROVIDER_2_TYPE": "anthropic", "PROVIDER_2_API_KEY": "k2", "PROVIDER_2_MODEL": "m2",
        "PROVIDER_2_BASE_URL": "https://p2.invalid",
        "PROVIDER_3_TYPE": "openai_compatible", "PROVIDER_3_API_KEY": "k3", "PROVIDER_3_MODEL": "m3",
        "PROVIDER_3_BASE_URL": "https://p3.invalid/v1",
    }

    with with_env(**provider_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.return_value = _fake_response(200, _openai_success_payload("Provider 1 result"))
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            check("Chain: provider 1 success is used directly", result.source == "ai")
            check("Chain: provider 1 success returns its text", result.text == "Provider 1 result")
            check("Chain: no failed attempts recorded on first-try success", result.attempts == [])

    with with_env(**provider_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.side_effect = [
                _fake_response(500),  # provider 1 fails
                _fake_response(200, _anthropic_success_payload("Provider 2 result")),  # provider 2 succeeds
            ]
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            check("Chain: falls through provider 1 failure to provider 2", result.source == "ai")
            check("Chain: provider 2 result used after provider 1 fails", result.text == "Provider 2 result")
            check("Chain: provider 1 failure recorded as an attempt", len(result.attempts) == 1)
            check("Chain: provider 1 failure category is 'unavailable' for 500", result.attempts[0].category == "unavailable")

    with with_env(**provider_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.side_effect = [
                _fake_response(401),  # provider 1: auth failure
                _fake_response(429),  # provider 2: quota failure
                _fake_response(200, _openai_success_payload("Provider 3 result")),  # provider 3 succeeds
            ]
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            check("Chain: falls through providers 1+2 to provider 3", result.source == "ai")
            check("Chain: provider 3 result used after 1+2 fail", result.text == "Provider 3 result")
            check("Chain: two failed attempts recorded", len(result.attempts) == 2)
            check("Chain: provider 1 auth failure categorized correctly", result.attempts[0].category == "auth")
            check("Chain: provider 2 quota failure categorized correctly", result.attempts[1].category == "quota")

    with with_env(**provider_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.side_effect = [
                _fake_response(500),
                _fake_response(500),
                _fake_response(500),
            ]
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            check("Chain: all providers failing falls back to local", result.source == "local_fallback")
            check("Chain: local fallback text is non-empty on all-fail", bool(result.text.strip()))
            check("Chain: ai_attempted is True when providers were tried", result.ai_attempted is True)
            check("Chain: three failed attempts recorded", len(result.attempts) == 3)

    with with_env(**provider_env) as ai_service:
        import requests as requests_module
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.side_effect = [requests_module.exceptions.Timeout()] * 3
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            check("Chain: network timeouts never crash the call", result.source == "local_fallback")
            check("Chain: timeout attempts categorized as 'timeout'", all(a.category == "timeout" for a in result.attempts))

    # ---- No providers configured at all ----
    with with_env(
        PROVIDER_1_API_KEY=None, PROVIDER_2_API_KEY=None, PROVIDER_3_API_KEY=None,
    ) as ai_service:
        result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
        check("No providers: falls back to local insights", result.source == "local_fallback")
        check("No providers: skip reason is 'not_configured'", result.ai_skipped_reason == "not_configured")
        check("No providers: ai_attempted is False (nothing to attempt)", result.ai_attempted is False)

    # ---- AI context size threshold (independent of upload cap) ----
    with with_env(VISORA_AI_CONTEXT_LIMIT_MB="100", **provider_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.return_value = _fake_response(200, _openai_success_payload("Should not be reached"))

            over_limit_bytes = 101 * 1024 * 1024
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=over_limit_bytes)
            check(">100MB: AI is never contacted", not mock_post.called)
            check(">100MB: result source is local_fallback", result.source == "local_fallback")
            check(">100MB: skip reason is size_threshold_exceeded", result.ai_skipped_reason == "size_threshold_exceeded")
            check(">100MB: ai_attempted is False", result.ai_attempted is False)

            mock_post.reset_mock()
            at_limit_bytes = 100 * 1024 * 1024
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=at_limit_bytes)
            check("==100MB boundary: AI chain IS attempted (<=, not <)", mock_post.called)
            check("==100MB boundary: succeeds via provider", result.source == "ai")

            mock_post.reset_mock()
            under_limit_bytes = 1024
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=under_limit_bytes)
            check("<100MB: AI chain is attempted", mock_post.called)

    # ---- Full analytical context reaches the provider untruncated ----
    # A large context (well over any old arbitrary char cap) must still
    # be sent to the provider in full when the file is <=100MB -- no
    # token-compression / context-trimming is in scope for this milestone.
    with with_env(**provider_env) as ai_service:
        large_context = dict(SAMPLE_CONTEXT)
        large_context["anomalies"] = {
            "available": True,
            "data": {"Sales": [{"row_id": i, "value": 9000 + i, "note": "x" * 200} for i in range(200)]},
        }
        import json as json_module
        serialized_size = len(json_module.dumps(large_context, indent=2))
        check("Large-context fixture actually exceeds the old 12000-char cap", serialized_size > 12000)

        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.return_value = _fake_response(200, _openai_success_payload("ok"))
            ai_service.generate_ai_insights(large_context, file_size_bytes=1000)
            check("Large context: a provider call was made", mock_post.called)
            sent_payload = mock_post.call_args.kwargs["json"]
            sent_prompt = sent_payload["messages"][-1]["content"]
            check(
                "Large context: the FULL serialized context (not a truncated prefix) is in the prompt",
                "... (truncated for prompt size)" not in sent_prompt
                and all(f'"row_id": {i}' in sent_prompt for i in (0, 50, 100, 150, 199)),
            )

    # ---- Local fallback never fabricates missing sections ----
    with with_env(
        PROVIDER_1_API_KEY=None, PROVIDER_2_API_KEY=None, PROVIDER_3_API_KEY=None,
    ) as ai_service:
        result = ai_service.generate_ai_insights(EMPTY_CONTEXT, file_size_bytes=1000)
        check("Empty context: local fallback does not crash", result.source == "local_fallback")
        check("Empty context: fallback text is non-empty", bool(result.text.strip()))
        check(
            "Empty context: fallback does not fabricate a trend/contribution/anomaly line",
            "%" not in result.text and "anomaly" not in result.text.lower(),
        )

        result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
        check("Populated context: local fallback mentions the top contributor", "Tech" in result.text)

    # ---- Provider abstraction never leaks the API key into an error ----
    with with_env(**provider_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.side_effect = [_fake_response(401)] * 3
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            all_messages = " ".join(a.message for a in result.attempts)
            check("Auth failure message never contains the raw API key", "k1" not in all_messages and "k2" not in all_messages)

    # ---- Google Gemini provider: correct request/response format ----
    gemini_env = {
        "PROVIDER_1_TYPE": "gemini", "PROVIDER_1_API_KEY": "gemini-key", "PROVIDER_1_MODEL": "gemini-1.5-flash",
        "PROVIDER_2_API_KEY": None, "PROVIDER_3_API_KEY": None,
    }
    with with_env(**gemini_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.return_value = _fake_response(200, _gemini_success_payload("Gemini result"))
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            check("Gemini: provider success is used", result.source == "ai")
            check("Gemini: returns provider text", result.text == "Gemini result")
            # Verify request format: API key as query param, correct endpoint, contents format
            called_url = mock_post.call_args.args[0]
            check("Gemini: URL contains model and API key param", "gemini-1.5-flash:generateContent" in called_url and "key=gemini-key" in called_url)
            sent_payload = mock_post.call_args.kwargs["json"]
            check("Gemini: payload uses 'contents' not 'messages'", "contents" in sent_payload and "messages" not in sent_payload)
            check("Gemini: payload has generationConfig", "generationConfig" in sent_payload)

    # ---- NVIDIA Nemotron provider: correct request/response format ----
    nemotron_env = {
        "PROVIDER_1_TYPE": "nemotron", "PROVIDER_1_API_KEY": "nemotron-key", "PROVIDER_1_MODEL": "nvidia/nemotron-3-ultra",
        "PROVIDER_2_API_KEY": None, "PROVIDER_3_API_KEY": None,
    }
    with with_env(**nemotron_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.return_value = _fake_response(200, _nemotron_success_payload("Nemotron result"))
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            check("Nemotron: provider success is used", result.source == "ai")
            check("Nemotron: returns provider text", result.text == "Nemotron result")
            # Verify request format: OpenAI-compatible with NVIDIA defaults
            called_url = mock_post.call_args.args[0]
            check("Nemotron: URL uses NVIDIA NIM endpoint", "integrate.api.nvidia.com/v1/chat/completions" in called_url)
            sent_payload = mock_post.call_args.kwargs["json"]
            check("Nemotron: payload uses 'messages' format", "messages" in sent_payload)
            check("Nemotron: payload includes system and user roles", sent_payload["messages"][0]["role"] == "system" and sent_payload["messages"][1]["role"] == "user")
            check("Nemotron: Authorization header is Bearer", mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer nemotron-key")

    # ---- Fallback chain with mixed provider types (OpenRouter -> Gemini -> Nemotron) ----
    mixed_env = {
        "PROVIDER_1_TYPE": "openai_compatible", "PROVIDER_1_API_KEY": "or-key", "PROVIDER_1_MODEL": "openai/gpt-4o-mini", "PROVIDER_1_BASE_URL": "https://openrouter.ai/api/v1",
        "PROVIDER_2_TYPE": "gemini", "PROVIDER_2_API_KEY": "gemini-key", "PROVIDER_2_MODEL": "gemini-1.5-flash",
        "PROVIDER_3_TYPE": "nemotron", "PROVIDER_3_API_KEY": "nemotron-key", "PROVIDER_3_MODEL": "nvidia/nemotron-3-ultra",
    }
    with with_env(**mixed_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.side_effect = [
                _fake_response(500),  # OpenRouter fails
                _fake_response(200, _gemini_success_payload("Gemini fallback result")),  # Gemini succeeds
            ]
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            check("Mixed chain: falls through OpenRouter failure to Gemini", result.source == "ai")
            check("Mixed chain: Gemini result used after OpenRouter fails", result.text == "Gemini fallback result")
            check("Mixed chain: one failed attempt recorded", len(result.attempts) == 1)
            check("Mixed chain: OpenRouter failure categorized as unavailable", result.attempts[0].category == "unavailable")

    # ---- Unrecognized provider type is skipped, not a crash ----
    with with_env(
        PROVIDER_1_TYPE="totally_unknown_vendor", PROVIDER_1_API_KEY="k1", PROVIDER_1_MODEL="m1",
        PROVIDER_2_API_KEY=None, PROVIDER_3_API_KEY=None,
    ) as ai_service:
        result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
        check("Unknown provider type: never crashes", result.source == "local_fallback")

    # ---- Malformed provider response ----
    with with_env(**provider_env) as ai_service:
        with patch("backend.ai_providers.requests.post") as mock_post:
            mock_post.side_effect = [
                _fake_response(200, {"unexpected": "shape"}),
                _fake_response(200, {"unexpected": "shape"}),
                _fake_response(200, {"unexpected": "shape"}),
            ]
            result = ai_service.generate_ai_insights(SAMPLE_CONTEXT, file_size_bytes=1000)
            check("Malformed response: never crashes", result.source == "local_fallback")
            check(
                "Malformed response: categorized as invalid_response",
                all(a.category == "invalid_response" for a in result.attempts),
            )

    # ---- Ingestion: unsupported/non-CSV content is rejected, not a crash ----
    import tempfile
    from backend.ingestion import DatasetIngestor

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = str(Path(tmp_dir) / "visora.db")
        ingestor = DatasetIngestor(db_file=db_file)
        ingestor.connect()

        binary_path = Path(tmp_dir) / "not_a_real.csv"
        binary_path.write_bytes(bytes(range(256)) * 4)  # arbitrary non-CSV binary content
        result = ingestor.ingest_csv(str(binary_path), "ds_binary_test")
        check("Ingestion: binary content disguised as .csv does not crash", isinstance(result, dict))
        check("Ingestion: binary content disguised as .csv is reported as not ingested", result["ingested"] is False)
        if ingestor.conn:
            ingestor.conn.close()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
