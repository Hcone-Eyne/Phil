"""
FILE: setup/llm_client.py

Unified LLM client for Phil. Replaces all direct ollama.chat() calls
throughout the codebase with a single interface that works for both
Local Mode (Ollama) and API Mode (Anthropic, OpenAI, Gemini, OpenRouter).

HOW TO USE:
    from setup.llm_client import LLMClient

    client = LLMClient()          # auto-reads phil_config.json
    response = client.chat(
        system="You are a FreeCAD expert.",
        user="Make a bolt.",
    )
    print(response)               # plain string — same regardless of backend

SWAPPING BACKENDS:
    The caller never needs to know which backend is running.
    ai_core.py and command_bridge.py just call client.chat() and get a string back.
    The config file controls which backend fires.

ADDING A NEW PROVIDER:
    1. Add its name to SUPPORTED_PROVIDERS
    2. Add a branch in _chat_api()
    3. Add its SDK to requirements.txt
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from voice_input.Keys import config as key_config

# ── Config path — same location as phil_config.json ──────────────────────────
# This mirrors what config.py will expose once extended.
_PROJECT_ROOT   = Path(__file__).resolve().parent.parent
_CONFIG_PATH = Path(
    getattr(
        key_config,
        "phil_config_path",
        _PROJECT_ROOT / "voice_input" / "Keys" / "phil_config.json",
    )
)
_ENV_PATH = Path(
    getattr(
        key_config,
        "env_path",
        _PROJECT_ROOT / "voice_input" / ".env",
    )
)

# ── Supported providers for API mode ─────────────────────────────────────────
SUPPORTED_PROVIDERS = ("anthropic", "openai", "gemini", "openrouter")

# ── Default models per provider ───────────────────────────────────────────────
# These are the best value models at time of writing.
# User can override via phil_config.json ("api_model" key).
DEFAULT_MODELS: dict[str, str] = {
    "anthropic":  "claude-sonnet-4-20250514",
    "openai":     "gpt-4o",
    "gemini":     "gemini-2.0-flash",
    "openrouter": "openai/gpt-4o",   # openrouter uses "provider/model" format
}


class LLMClient:
    """
    Single interface for all LLM backends.

    Phil's code calls client.chat(system=..., user=...) everywhere.
    This class reads phil_config.json and routes to the right backend.

    Attributes:
        mode      — "local" or "api"
        provider  — "anthropic" / "openai" / "gemini" / "openrouter" / None
        model     — the model string being used (e.g. "qwen2.5-coder:7b")
    """

    def __init__(self, config_path: Path | None = None):
        # Allow passing a custom config path for testing
        self._config_path = config_path or _CONFIG_PATH
        self._config      = self._load_config()

        # Resolve mode and provider from config
        self.mode     = self._config.get("mode", "local")
        self.provider = self._config.get("provider", None)

        # Resolve which model to use
        if self.mode == "local":
            # Local mode: use the model that was pulled during setup
            self.model = self._config.get("local_model", "qwen2.5-coder:7b")
        else:
            # API mode: use configured model or fall back to provider default
            self.model = self._config.get("api_model") or DEFAULT_MODELS.get(self.provider or "", "")

        # Load .env so API keys are available as environment variables
        self._load_env()

        print(f"[LLMClient] Mode: {self.mode} | Model: {self.model} | Provider: {self.provider}")

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(
        self,
        system: str,
        user: str,
        *,
        format_json: bool = False,
        max_tokens: int = 2048,
        timeout: float = 120.0,
    ) -> str:
        """
        Send a chat message and return the response as a plain string.

        Args:
            system      — system prompt (instructions for the model)
            user        — user message (the actual request)
            format_json — if True, hint to the model to return only JSON
                          (uses Ollama's native format="json" in local mode)
            max_tokens  — maximum tokens in the response
            timeout     — timeout in seconds for the request

        Returns:
            The model's response as a plain string.
            Raises LLMError on unrecoverable failure.
        """
        if self.mode == "local":
            return self._chat_local(system, user, format_json=format_json, timeout=timeout)
        else:
            return self._chat_api(system, user, max_tokens=max_tokens, timeout=timeout)

    def is_ready(self) -> bool:
        """
        Quick health check — returns True if the backend is reachable.
        Used by setup_screen to validate before letting the user proceed.
        """
        try:
            response = self.chat(
                system="Respond with the word ok.",
                user="ok?",
                max_tokens=10,
            )
            return bool(response and response.strip())
        except Exception:
            return False

    # ── Local Mode (Ollama) ───────────────────────────────────────────────────

    def _chat_local(self, system: str, user: str, *, format_json: bool, timeout: float = 120.0) -> str:
        """
        Route to Ollama running locally.

        Uses format="json" when format_json=True — this is constrained decoding:
        Ollama forces the model to output valid JSON at the token level,
        so it physically cannot return thoughts/steps/markdown.
        This is the permanent fix for the JSON format failures.
        """
        try:
            import ollama  # type: ignore
        except ImportError:
            raise LLMError("ollama Python package is not installed. Run: pip install ollama")

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        }

        # format="json" = constrained decoding — only valid JSON tokens allowed
        if format_json:
            kwargs["format"] = "json"

        try:
            try:
                client = ollama.Client(timeout=timeout)
                response = client.chat(**kwargs)
            except AttributeError:
                # Fallback for older versions of ollama package
                response = ollama.chat(**kwargs)
            return response.message.content
        except Exception as exc:
            raise LLMError(f"Ollama chat failed: {exc}") from exc

    # ── API Mode ──────────────────────────────────────────────────────────────

    def _chat_api(self, system: str, user: str, *, max_tokens: int, timeout: float = 120.0) -> str:
        """
        Route to the configured API provider.
        Each provider has its own SDK but the same input/output contract.
        """
        if self.provider == "anthropic":
            return self._chat_anthropic(system, user, max_tokens=max_tokens, timeout=timeout)
        elif self.provider == "openai":
            return self._chat_openai(system, user, max_tokens=max_tokens, timeout=timeout)
        elif self.provider == "gemini":
            return self._chat_gemini(system, user, max_tokens=max_tokens, timeout=timeout)
        elif self.provider == "openrouter":
            return self._chat_openrouter(system, user, max_tokens=max_tokens, timeout=timeout)
        else:
            raise LLMError(f"Unknown provider: {self.provider!r}. Choose from {SUPPORTED_PROVIDERS}")

    def _chat_anthropic(self, system: str, user: str, *, max_tokens: int, timeout: float = 120.0) -> str:
        """Anthropic Claude via official SDK."""
        try:
            import anthropic  # type: ignore
        except ImportError:
            raise LLMError("anthropic package not installed. Run: pip install anthropic")

        api_key = self._get_api_key("ANTHROPIC_API_KEY")
        client  = anthropic.Anthropic(api_key=api_key, timeout=timeout)

        message = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Anthropic returns a list of content blocks — join all text blocks
        return "".join(
            block.text for block in message.content
            if hasattr(block, "text")
        )

    def _chat_openai(self, system: str, user: str, *, max_tokens: int, timeout: float = 120.0) -> str:
        """OpenAI GPT via official SDK."""
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise LLMError("openai package not installed. Run: pip install openai")

        api_key = self._get_api_key("OPENAI_API_KEY")
        client  = OpenAI(api_key=api_key, timeout=timeout)

        completion = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return completion.choices[0].message.content or ""

    def _chat_gemini(self, system: str, user: str, *, max_tokens: int, timeout: float = 120.0) -> str:
        """Google Gemini via google-generativeai SDK."""
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError:
            raise LLMError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )

        api_key = self._get_api_key("GEMINI_API_KEY")
        genai.configure(api_key=api_key)

        # Gemini combines system + user into a single prompt
        # because its Python SDK handles system instructions differently
        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system,
        )
        response = model.generate_content(
            user,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
            ),
            request_options={"timeout": timeout},
        )
        return response.text or ""

    def _chat_openrouter(self, system: str, user: str, *, max_tokens: int, timeout: float = 120.0) -> str:
        """
        OpenRouter via their OpenAI-compatible API.
        OpenRouter supports hundreds of models under one API key.
        Model string format: "provider/model" e.g. "openai/gpt-4o"
        """
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise LLMError("openai package not installed. Run: pip install openai")

        api_key = self._get_api_key("OPENROUTER_API_KEY")

        # OpenRouter uses OpenAI's SDK but with a different base URL
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout,
        )

        completion = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return completion.choices[0].message.content or ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        """
        Load phil_config.json. Returns empty dict if not found —
        first run before setup completes.
        """
        if not self._config_path.exists():
            return {}
        try:
            with open(self._config_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_env(self):
        """
        Load .env file into environment variables.
        We do this manually to avoid requiring python-dotenv as a hard dependency.
        Keys already set in the environment are NOT overwritten
        (so real env vars always win over .env).
        """
        if not _ENV_PATH.exists():
            return
        try:
            with open(_ENV_PATH, "r") as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and blank lines
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key   = key.strip()
                    value = value.strip().strip('"').strip("'")
                    # Don't overwrite real environment variables
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception:
            pass  # .env read failure is non-fatal

    def _get_api_key(self, env_var: str) -> str:
        """
        Get an API key from environment variables.
        Raises LLMError with a clear message if missing.
        """
        key = os.environ.get(env_var, "").strip()
        if not key:
            raise LLMError(
                f"API key not found. Set {env_var} in your .env file.\n"
                f"Example: {env_var}=your_key_here"
            )
        return key


# ── Custom exception ──────────────────────────────────────────────────────────

class LLMError(Exception):
    """
    Raised when the LLM backend fails in a way the caller should handle.
    Distinct from generic Exception so callers can catch it specifically.
    """
    pass


# ── Convenience function for callers that just want a quick client ────────────
_cached_client: LLMClient | None = None
_cached_config_mtime: float | None = None


def _config_mtime() -> float | None:
    try:
        return _CONFIG_PATH.stat().st_mtime
    except Exception:
        return None


def invalidate_client_cache():
    """Call this when phil_config.json changes (e.g., after mode switch)."""
    global _cached_client, _cached_config_mtime
    _cached_client = None
    _cached_config_mtime = None


def get_client() -> LLMClient:
    """
    Returns a ready LLMClient using the current phil_config.json.
    Caches the instance so config is only read once per session.
    Automatically invalidates cache if config file mtime changes.
    Use this in ai_core.py and command_bridge.py instead of importing
    the class directly — makes testing and mocking easier.

    Usage:
        from setup.llm_client import get_client
        client = get_client()
        response = client.chat(system=..., user=...)
    """
    global _cached_client, _cached_config_mtime
    current_mtime = _config_mtime()
    if _cached_client is None or current_mtime != _cached_config_mtime:
        _cached_client = LLMClient()
        _cached_config_mtime = current_mtime
    return _cached_client
