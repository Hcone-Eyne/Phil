# ============================================================
# FILE: voice_input/command_bridge.py
# PURPOSE: Bridge between user input and the AI + FreeCAD runner.
#          Both voice and text input funnel through here.
# ============================================================

from voice_input.cad_assist.ai_core import translator
from voice_input.cad_assist import runner
import ollama

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
    generated_script = translator(user_input)

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


def self_corrector(script_path, error_message):
    with open(script_path, "r") as file:
        error_code = file.read()

    fixing_prompt = (
        f"The following FreeCAD script failed with an error.\n"
        f"ERROR: {error_message}\n"
        f"FAILED CODE:\n{error_code}\n"
        f"Please provide only the corrected Python code that fixes this specific error. "
        f"Maintain the same header and footer rules."
    )

    response = ollama.chat(
        model="qwen2.5-coder:7b",
        messages=[
            {"role": "system", "content": "You are a FreeCAD Python debugger. Return ONLY raw code."},
            {"role": "user",   "content": fixing_prompt},
        ],
    )

    raw_fix   = response.message.content
    clean_fix = raw_fix.replace("```python", "").replace("```", "").strip()
    return clean_fix