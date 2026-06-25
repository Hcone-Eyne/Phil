"""Install and verify Ollama models for Phil's Local Mode.

Student testing notes:
    Check whether Ollama is installed:
        venv/bin/python -c "from setup.installer import install_ollama; print(install_ollama(dry_run=True))"

    Check whether a model is already pulled:
        venv/bin/python -c "from setup.installer import is_model_pulled; print(is_model_pulled('qwen2.5-coder:7b'))"

    Pull a model and print progress:
        venv/bin/python -c "from setup.installer import pull_model; print(pull_model('qwen2.5-coder:7b', print))"

    Verify a model responds:
        venv/bin/python -c "from setup.installer import verify_ollama; print(verify_ollama('qwen2.5-coder:7b', print))"
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import webbrowser
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


ProgressCallback = Callable[[str], None]

DEFAULT_MODEL = "qwen2.5-coder:7b"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"

_SETUP_DIR = Path(__file__).resolve().parent
_REQUIREMENTS_FILE = _SETUP_DIR / "requirements.txt"

# Pip package for each API provider slug (matches setup_screen / llm_client)
API_PROVIDER_PACKAGES: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "gemini": "google-generativeai",
    "openrouter": "openai",
}

PACKAGE_IMPORTS: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google-generativeai": "google.generativeai",
    "ollama": "ollama",
}


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    detail: str
    command: list[str] | None = None


def install_setup_requirements(
    progress_callback: ProgressCallback | None = None,
) -> InstallResult:
    """Install shared packages from setup/requirements.txt."""
    if _running_frozen():
        return InstallResult(ok=True, detail="Shared dependencies are bundled with Phil.")

    if not _REQUIREMENTS_FILE.exists():
        return InstallResult(ok=False, detail=f"Missing requirements file: {_REQUIREMENTS_FILE}")

    _progress(progress_callback, "Installing shared Python dependencies…")
    command = [sys.executable, "-m", "pip", "install", "-r", str(_REQUIREMENTS_FILE)]
    ok = _run_streaming_command(command, progress_callback)
    return InstallResult(
        ok=ok,
        detail="Shared dependencies installed." if ok else "Failed to install shared dependencies.",
        command=command,
    )


def install_api_provider_package(
    provider: str,
    progress_callback: ProgressCallback | None = None,
) -> InstallResult:
    """Install the SDK pip package for the chosen API provider."""
    package = API_PROVIDER_PACKAGES.get(provider.lower().strip())
    if not package:
        return InstallResult(
            ok=False,
            detail=f"Unknown API provider '{provider}'. Supported: {', '.join(API_PROVIDER_PACKAGES)}",
        )
    return pip_install_package(package, progress_callback)


def pip_install_package(
    package: str,
    progress_callback: ProgressCallback | None = None,
) -> InstallResult:
    """Install a single pip package into the current interpreter."""
    if _running_frozen():
        module_name = PACKAGE_IMPORTS.get(package, package.replace("-", "_"))
        if importlib.util.find_spec(module_name) is not None:
            return InstallResult(ok=True, detail=f"{package} is bundled with Phil.")
        return InstallResult(
            ok=False,
            detail=f"{package} is not bundled in this Phil build. Rebuild the app with this dependency included.",
        )

    _progress(progress_callback, f"Installing {package}…")
    command = [sys.executable, "-m", "pip", "install", package]
    ok = _run_streaming_command(command, progress_callback)
    return InstallResult(
        ok=ok,
        detail=f"{package} installed." if ok else f"Failed to install {package}.",
        command=command,
    )


def install_ollama(
    progress_callback: ProgressCallback | None = None,
    *,
    dry_run: bool = False,
    prefer_brew: bool = True,
) -> InstallResult:
    """Install Ollama when possible, or guide the user to the installer.

    This function is intentionally user-confirmation friendly. The future setup
    UI should call it only after the user chooses Local Mode and confirms.
    """
    _progress(progress_callback, "Checking for Ollama...")
    if shutil.which("ollama"):
        return InstallResult(ok=True, detail="Ollama is already installed.")

    system = platform.system()
    if system == "Darwin":
        return _install_ollama_mac(progress_callback, dry_run=dry_run, prefer_brew=prefer_brew)

    if system == "Windows":
        return _open_download_page(progress_callback, dry_run=dry_run)

    if system == "Linux":
        return InstallResult(
            ok=False,
            detail="Automatic Linux install is not wired yet. Open https://ollama.com/download and install Ollama.",
        )

    return InstallResult(
        ok=False,
        detail=f"Unsupported platform for automatic install: {system or 'unknown'}",
    )


def pull_model(
    model_name: str = DEFAULT_MODEL,
    progress_callback: ProgressCallback | None = None,
) -> bool:
    """Pull an Ollama model, streaming progress lines to the callback."""
    if not shutil.which("ollama"):
        _progress(progress_callback, "Ollama is not installed.")
        return False

    if is_model_pulled(model_name):
        _progress(progress_callback, f"{model_name} is already pulled.")
        return True

    _progress(progress_callback, f"Pulling {model_name}...")
    return _run_streaming_command(
        ["ollama", "pull", model_name],
        progress_callback,
    )


def verify_ollama(
    model_name: str = DEFAULT_MODEL,
    progress_callback: ProgressCallback | None = None,
) -> bool:
    """Ask Ollama for a tiny response so we know Local Mode can actually run."""
    if not shutil.which("ollama"):
        _progress(progress_callback, "Ollama is not installed.")
        return False

    _progress(progress_callback, f"Verifying {model_name}...")
    try:
        result = subprocess.run(
            ["ollama", "run", model_name, "respond ok"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _progress(progress_callback, f"Verification failed: {exc}")
        return False

    output = (result.stdout or result.stderr or "").strip()
    if output:
        _progress(progress_callback, output)

    return result.returncode == 0 and "ok" in output.lower()


def is_model_pulled(model_name: str) -> bool:
    """Return True when `ollama list` already contains the requested model."""
    if not shutil.which("ollama"):
        return False

    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    if result.returncode != 0:
        return False

    requested_has_tag = ":" in model_name
    requested_base = model_name.split(":", 1)[0]
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        pulled_name = parts[0] if parts else ""
        pulled_base = pulled_name.split(":", 1)[0]
        if requested_has_tag and pulled_name == model_name:
            return True
        if not requested_has_tag and pulled_base == requested_base:
            return True
    return False


def _install_ollama_mac(
    progress_callback: ProgressCallback | None,
    *,
    dry_run: bool,
    prefer_brew: bool,
) -> InstallResult:
    if prefer_brew and shutil.which("brew"):
        command = ["brew", "install", "ollama"]
        if dry_run:
            return InstallResult(ok=True, detail="Would install Ollama with Homebrew.", command=command)

        _progress(progress_callback, "Installing Ollama with Homebrew...")
        ok = _run_streaming_command(command, progress_callback)
        return InstallResult(
            ok=ok,
            detail="Ollama installed with Homebrew." if ok else "Homebrew install failed.",
            command=command,
        )

    return _open_download_page(progress_callback, dry_run=dry_run)


def _open_download_page(
    progress_callback: ProgressCallback | None,
    *,
    dry_run: bool,
) -> InstallResult:
    if dry_run:
        return InstallResult(
            ok=True,
            detail=f"Would open Ollama download page: {OLLAMA_DOWNLOAD_URL}",
        )

    _progress(progress_callback, "Opening Ollama download page...")
    webbrowser.open(OLLAMA_DOWNLOAD_URL)
    return InstallResult(
        ok=False,
        detail="Opened Ollama download page. Run setup again after installing.",
    )


def _run_streaming_command(
    command: list[str],
    progress_callback: ProgressCallback | None,
) -> bool:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        _progress(progress_callback, f"Could not start command: {exc}")
        return False

    assert process.stdout is not None
    for line in process.stdout:
        clean_line = line.strip()
        if clean_line:
            _progress(progress_callback, clean_line)

    return process.wait() == 0


def _progress(progress_callback: ProgressCallback | None, message: str) -> None:
    print(f"[Installer] {message}")
    if progress_callback:
        progress_callback(message)


def _running_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


if __name__ == "__main__":
    result = install_ollama(print, dry_run=True)
    print(result)
