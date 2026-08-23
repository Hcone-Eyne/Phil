# ============================================================
# FILE: voice_input/command_bridge.py
# PURPOSE: Bridge between user input and the AI + FreeCAD runner.
#          Both voice and text input funnel through here.
# ============================================================

from voice_input.cad_assist.ai_core import translator
from voice_input.cad_assist import runner
from setup.llm_client import get_client  # unified LLM backend

EXIT_COMMANDS = {"exit", "exits", "quit", "q"}


def process_command(user_input: str, status_callback=None) -> bool:
    """
    Takes a text command and:
      1. Sends it to the AI to generate a FreeCAD Python script.
      2. Runs the generated script in FreeCAD.

    status_callback(message: str) is passed all the way down to runner
    so the UI gets live updates at every stage.

    Returns True if successful, False otherwise.
    """

    def report(msg: str):
        print(f"[Bridge] {msg}")
        if status_callback:
            status_callback(msg)

    if not user_input or not user_input.strip():
        report("Empty input — ignoring.")
        return False

    if user_input.strip().lower() in EXIT_COMMANDS:
        report("Exit command received.")
        return False

    report("Sending to AI…")
    generated_script = translator(user_input, status_callback=status_callback)

    if not generated_script:
        report("AI failed to generate a script.")
        return False

    report("Script ready — launching FreeCAD…")
    success = runner.execute_cad_scripts(
        generated_script,
        user_input,
        status_callback=status_callback,   # ← live updates flow to UI
    )

    if success:
        report("All done!")
    return success