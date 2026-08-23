import os
import shutil
import sys
from pathlib import Path

# ── Project root: voice_input/ ───────────────────────────────────────────────
master_root = Path(__file__).resolve().parent.parent
project_root = master_root.parent


def _platform_data_root() -> Path:
    """Return a writable per-user data directory for packaged builds."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Phil"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / "Phil"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "Phil"


def _first_existing(*candidates: str | Path | None) -> Path | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def _resolve_freecad_cmd() -> str:
    found = _first_existing(
        os.environ.get("FREECAD_CMD"),
        "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd",
        shutil.which("freecadcmd"),
        shutil.which("FreeCADCmd"),
        "/usr/local/bin/freecadcmd",
        "/opt/homebrew/bin/freecadcmd",
    )
    return str(found) if found else "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"


def _resolve_freecad_gui() -> str:
    found = _first_existing(
        os.environ.get("FREECAD_GUI"),
        "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD",
        "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd",
    )
    return str(found) if found else "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD"


def _resolve_blender_cmd() -> str:
    found = _first_existing(
        os.environ.get("BLENDER_CMD"),
        "/Applications/Blender.app/Contents/MacOS/Blender",
        shutil.which("blender"),
    )
    return str(found) if found else "/Applications/Blender.app/Contents/MacOS/Blender"


is_frozen = bool(getattr(sys, "frozen", False))
runtime_root = _platform_data_root() if is_frozen else master_root

# ── External app paths (override with FREECAD_CMD / FREECAD_GUI / BLENDER_CMD) ─
free_cad_cmd = _resolve_freecad_cmd()
free_cad_gui = _resolve_freecad_gui()
blender_cmd = _resolve_blender_cmd()

# ── Standard folder paths ────────────────────────────────────────────────────
script_location = master_root / "scripts"
output_location = runtime_root / "output"
key_location = runtime_root / "Keys"
logs_location = runtime_root / "logs"
data_location = runtime_root / "data"
memory_path = logs_location / "memory" / "memory.json"
phil_config_path = key_location / "phil_config.json"
env_path = runtime_root / ".env"

# ── AI-generated artefacts ───────────────────────────────────────────────────
ai_gen_folder = runtime_root / "scripts" / "ai_generated_scripts"
ai_gen_script = ai_gen_folder / "ai_gen_script.py"

# ── Speech processor module path (directory, not a .py file) ─────────────────
The_listener = master_root.parent / "speech_processor"

# ── CAD assist module path (source code — read-only in bundled builds) ───────
cad_assist_location = master_root / "cad_assist"

# ── AI core persistence (writable runtime data) ──────────────────────────────
error_memory_path = logs_location / "error_memory.json"
generated_asset_library_path = data_location / "generated_asset_library.json"
correction_log_path = logs_location / "correction.log.txt"

phil_config = phil_config_path

for _folder in (
    output_location,
    key_location,
    logs_location,
    data_location,
    memory_path.parent,
    ai_gen_folder,
):
    _folder.mkdir(parents=True, exist_ok=True)

# Migrate asset library out of bundled cad_assist/ (older builds wrote there).
_legacy_asset_library = cad_assist_location / "generated_asset_library.json"
if not generated_asset_library_path.exists() and _legacy_asset_library.exists():
    shutil.copy2(_legacy_asset_library, generated_asset_library_path)
