from pathlib import Path

# ── FreeCAD headless command ─────────────────────────────────────────────────
free_cad_cmd = "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"

# ── Project root: voice_input/ ───────────────────────────────────────────────
master_root = Path(__file__).resolve().parent.parent
project_root = master_root.parent

# ── Standard folder paths ────────────────────────────────────────────────────
script_location    = master_root / "scripts"
output_location    = master_root / "output"
key_location       = master_root / "Keys"
logs_location      = master_root / "logs"
memory_path        = master_root / "logs" / "memory" / "memory.json"
phil_config_path   = key_location / "phil_config.json"
env_path           = master_root / ".env"

# ── AI-generated artefacts ───────────────────────────────────────────────────
ai_gen_folder = master_root / "scripts" / "ai_generated_scripts"
ai_gen_script = ai_gen_folder / "ai_gen_script.py"

# ── Speech processor module path (directory, not a .py file) ─────────────────
# FIX: was pointing to voice_handler (a .py module) — now points to the package
The_listener = master_root.parent / "speech_processor"

# ── CAD assist module path ───────────────────────────────────────────────────
cad_assist_location = master_root / "cad_assist"
# NOTE: removed bare print() — it ran on every import and polluted logs

# ── AI core persistence (error memory, asset library, runtime corrections) ───
error_memory_path = logs_location / "error_memory.json"
generated_asset_library_path = cad_assist_location / "generated_asset_library.json"
correction_log_path = logs_location / "correction.log.txt"

# ── Phil config path ───────────────────────────────────────────────────────────
phil_config = master_root.parent / "phil_config.json"

# Env path ─────────────────────────────────────────────────────────────────────

#