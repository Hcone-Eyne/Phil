"""System capability checks used before Phil's first-run setup.

Student testing notes:
    Run this file directly from the project root:
        venv/bin/python -m setup.system_check

    Or test one function from the terminal:
        venv/bin/python -c "from setup.system_check import run_system_check; print(run_system_check().to_dict())"

The functions in this module only inspect the machine. They do not install
software, pull models, or mutate user settings.
"""

from __future__ import annotations

import os
import json
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


LOCAL_RAM_MIN_GB = 8

MODEL_BY_RAM = (
    (16, "qwen2.5-coder:14b"),
    (8, "qwen2.5-coder:7b"),
    (4, "qwen2.5-coder:3b"),
)


@dataclass(frozen=True)
class CheckStatus:
    ok: bool
    detail: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SystemReport:
    ram: CheckStatus
    ollama: CheckStatus
    freecad: CheckStatus
    recommended_model: str | None
    viable_modes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ram": self.ram.to_dict(),
            "ollama": self.ollama.to_dict(),
            "freecad": self.freecad.to_dict(),
            "recommended_model": self.recommended_model,
            "viable_modes": self.viable_modes,
        }


def check_ram() -> CheckStatus:
    ram_gb = _total_ram_gb()
    if ram_gb is None:
        return CheckStatus(
            ok=False,
            detail="Could not determine installed RAM.",
            value=None,
        )

    return CheckStatus(
        ok=ram_gb >= LOCAL_RAM_MIN_GB,
        detail=f"{ram_gb:.1f} GB RAM detected.",
        value=round(ram_gb, 1),
    )


def check_ollama() -> CheckStatus:
    executable = _find_ollama_executable()
    if not executable:
        return CheckStatus(
            ok=False,
            detail="Ollama required.",
            value={"path": None, "server_running": False, "models": []},
        )

    models, error = _list_ollama_models(executable)
    if error:
        return CheckStatus(
            ok=True,
            detail=f"Ollama is installed but not running — open Ollama.app first. {error}",
            value={"path": executable, "server_running": False, "models": models},
        )

    return CheckStatus(
        ok=True,
        detail="Ollama is installed.",
        value={"path": executable, "server_running": True, "models": models},
    )


def check_freecad(configured_path: str | Path | None = None) -> CheckStatus:
    candidates = _freecad_candidates(configured_path)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return CheckStatus(
                ok=True,
                detail="FreeCAD command was found.",
                value=str(candidate),
            )

    path_candidate = shutil.which("freecadcmd") or shutil.which("FreeCADCmd")
    if path_candidate:
        return CheckStatus(
            ok=True,
            detail="FreeCAD command was found on PATH.",
            value=path_candidate,
        )

    return CheckStatus(
        ok=False,
        detail="FreeCAD command was not found.",
        value=None,
    )


def get_recommended_model(ram_gb: float | int | None) -> str | None:
    if ram_gb is None:
        return None

    for minimum_gb, model in MODEL_BY_RAM:
        if ram_gb >= minimum_gb:
            return model
    return None


def run_system_check(configured_freecad_path: str | Path | None = None) -> SystemReport:
    ram = check_ram()
    ollama = check_ollama()
    freecad = check_freecad(configured_freecad_path)

    recommended_model = get_recommended_model(ram.value)
    viable_modes = ["api"]
    if ram.ok:
        viable_modes.insert(0, "local")

    return SystemReport(
        ram=ram,
        ollama=ollama,
        freecad=freecad,
        recommended_model=recommended_model,
        viable_modes=viable_modes,
    )


def _total_ram_gb() -> float | None:
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return pages * page_size / (1024**3)
        except (OSError, ValueError):
            pass

    if platform.system() == "Darwin":
        try:
            output = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                text=True,
                timeout=2,
            )
            return int(output.strip()) / (1024**3)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    return None


def _find_ollama_executable() -> str | None:
    configured = os.environ.get("OLLAMA_BIN", "").strip()
    candidates = [
        configured,
        shutil.which("ollama"),
        "/opt/homebrew/bin/ollama",
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
        "/Applications/Ollama.app/Contents/Resources/ollama",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def _list_ollama_models(executable: str) -> tuple[list[str], str | None]:
    try:
        result = subprocess.run(
            [executable, "list"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], str(exc)

    output = result.stdout.strip()
    if result.returncode != 0:
        error = (result.stderr or output or "ollama list failed").strip()
        return [], error

    return _parse_ollama_list_output(output), None


def _parse_ollama_list_output(output: str) -> list[str]:
    models: list[str] = []
    if not output:
        return models

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        items = parsed.get("models", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    models.append(item["name"])
        return models

    for line in output.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue
        first_col = clean_line.split(maxsplit=1)[0]
        if first_col.upper() in {"NAME", "MODEL"}:
            continue
        if ":" in first_col or "/" in first_col:
            models.append(first_col)
    
    return models


def _freecad_candidates(configured_path: str | Path | None) -> list[Path]:
    candidates: list[Path] = []
    if configured_path:
        candidates.append(Path(configured_path))

    candidates.extend(
        [
            Path("/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"),
            Path("/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd"),
            Path("/usr/local/bin/freecadcmd"),
            Path("/opt/homebrew/bin/freecadcmd"),
            Path("/usr/bin/freecadcmd"),
            Path("C:/Program Files/FreeCAD/bin/FreeCADCmd.exe"),
        ]
    )
    return candidates


if __name__ == "__main__":
    import json

    print(json.dumps(run_system_check().to_dict(), indent=2))
