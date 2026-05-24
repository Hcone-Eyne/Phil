"""
FILE: voice_input/main.py

Entry point for Phil.

On first launch (setup_complete = false in phil_config.json):
    → shows setup_screen.py (system check, mode choice, install)

On subsequent launches (setup_complete = true):
    → loads phil_config.json and goes straight to Phil UI

Threading rule: mainloop() must run on the main thread — mandatory on macOS.
"""

import json
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ── Config location ───────────────────────────────────────────────────────────
# phil_config.json lives in voice_input/Keys so it matches setup_screen.py,
# llm_client.py, and the original setup plan.
from voice_input.Keys import config as key_config

_CONFIG_PATH = Path(
    getattr(
        key_config,
        "phil_config_path",
        project_root / "voice_input" / "Keys" / "phil_config.json",
    )
)


def _load_config() -> dict:
    """
    Load phil_config.json.
    Returns default config if file is missing — handles very first launch
    before setup has ever run.
    """
    if not _CONFIG_PATH.exists():
        return {"setup_complete": False}
    try:
        with open(_CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        # Corrupted config — treat as fresh install
        return {"setup_complete": False}


def _launch_setup():
    """
    Show the first-run setup screen.
    setup_screen.py handles everything: system check, mode choice,
    install progress, and writing phil_config.json when done.
    After setup completes it calls _launch_phil() directly.
    """
    print("[Main] First launch — starting setup...")
    from setup.setup_screen import SetupScreen
    app = SetupScreen(on_complete=_launch_phil)
    app.mainloop()


def _launch_phil():
    """
    Launch the main Phil UI.
    Called directly on normal launch, or by setup_screen after setup finishes.
    """
    print("[Main] Starting Phil...")
    from ui.phil_overlay import Phil_Overlay
    app = Phil_Overlay()
    app.mainloop()
    print("[Main] Exited cleanly.")


if __name__ == "__main__":
    config = _load_config()

    if not config.get("setup_complete", False):
        # First launch or reset — show setup
        _launch_setup()
    else:
        # Already set up — go straight to Phil
        _launch_phil()
