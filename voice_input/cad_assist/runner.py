''' runner.py — sandbox executor with UI status callbacks.
If any error occurs, runner.py tries to self-correct up to 3 times.
All progress is reported via an optional status_callback(message: str)
so the UI can display live feedback instead of relying on terminal output. '''

import subprocess
import os
from pathlib import Path
import sys
import traceback
import ast

from voice_input.Keys.config import (
    output_location, script_location, logs_location,
    free_cad_cmd, ai_gen_script, ai_gen_folder, correction_log_path,
)

# Ensure output and log folders exist
for folder in [output_location, logs_location]:
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def defense_wall(script_path):
    with open(script_path, "r") as file:
        lines = file.readlines()

    cleaned_lines = []
    forbidden = [".remove(", "ActiveDocument.removeObject", "del "]
    for line in lines:
        if any(key in line for key in forbidden):
            continue
        cleaned_lines.append(line.rstrip())

    full_code = "\n".join(cleaned_lines)

    with open(script_path, "w") as file:
        file.write(full_code)

    try:
        ast.parse(full_code)
        return True
    except SyntaxError as e:
        print(f"[Runner] Syntax error in generated script: {e}")
        with open(logs_location / "error.report.txt", "w") as file:
            file.write(f"syntax_error:{e}")
        return False


def correction_runner(script_path):
    return subprocess.run(
        [free_cad_cmd, str(script_path)],
        capture_output=True,
        text=True,
        timeout=20,
    )


def script_verifier(result):
    return (
        result.returncode == 0
        and "Exception" not in result.stderr
        and "Error"     not in result.stderr
        and "Exception" not in result.stdout
        and "Error"     not in result.stdout
    )


def error_catcher(result):
    if result.stderr and result.stderr.strip():
        return result.stderr
    if result.stdout and result.stdout.strip():
        return result.stdout
    return "Unknown Error"


# ── main executor ─────────────────────────────────────────────────────────────

def execute_cad_scripts(script_name, user_request, status_callback=None):
    """
    Run an AI-generated FreeCAD script, self-correcting up to 3 times on failure.

    status_callback(message: str) — called at every meaningful stage so the UI
    can show live progress. Defaults to print() if not provided.
    """

    # Use print as fallback so terminal still works during dev
    def report(msg: str):
        print(f"[Runner] {msg}")
        if status_callback:
            status_callback(msg)

    from voice_input.command_bridge import self_corrector

    script_path_use = ai_gen_folder / script_name
    log_report      = logs_location / "error.report.txt"
    correction_log = correction_log_path

    # ── Step 1: Defense wall (syntax check) ───────────────────────────────────
    report("Checking script…")
    if not defense_wall(script_path_use):
        report("Syntax error — cannot run script")
        with open(log_report, "a") as f:
            f.write(f"Syntax_Error in {script_name}\n")
            f.write(traceback.format_exc())
        return False

    # ── Step 2: First run ─────────────────────────────────────────────────────
    report("Running in FreeCAD…")
    try:
        result = correction_runner(script_path_use)
    except subprocess.TimeoutExpired:
        report("Timed out — script may have an infinite loop")
        with open(log_report, "w") as f:
            f.write("Error: Execution Time Exceeded")
        return False

    if script_verifier(result):
        report("Done! ✓")
        with open(log_report, "w") as f:
            f.write("Last Run:\n")
            f.write(result.stdout)
        from voice_input import stage_manager
        stage_manager.script_saver(script_name, open(script_path_use).read(), user_request)
        return True

    # ── Step 3: Self-correction loop ──────────────────────────────────────────
    error_message = error_catcher(result)
    max_attempts  = 3
    fixed         = False

    with open(correction_log, "a") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"USER REQUEST: {user_request}\n")
        f.write(f"SCRIPT: {script_name}\n")
        f.write(f"ORIGINAL ERROR:\n{error_message}\n")

    for attempt in range(1, max_attempts + 1):
        report(f"Self-correcting… attempt {attempt}/{max_attempts}")

        try:
            new_code = self_corrector(script_path_use, error_message)
        except Exception as e:
            report(f"Corrector unavailable: {e}")
            with open(correction_log, "a") as f:
                f.write(f"\nSELF CORRECTION UNAVAILABLE:\n{e}\n")
            break

        with open(script_path_use, "w") as f:
            f.write(new_code)

        with open(correction_log, "a") as f:
            f.write(f"\nATTEMPT {attempt} - FIXED CODE:\n{new_code}\n")

        defense_wall(script_path_use)

        report(f"Retrying after fix {attempt}/{max_attempts}…")
        try:
            retry_result = correction_runner(script_path_use)
        except subprocess.TimeoutExpired:
            report("Timed out on retry")
            break

        if script_verifier(retry_result):
            report("Fixed! ✓")
            fixed = True
            with open(correction_log, "a") as f:
                f.write("PASS\n══════════════════════════\n")
            from voice_input import stage_manager
            stage_manager.script_saver(script_name, open(script_path_use).read(), user_request)
            break
        else:
            report(f"Attempt {attempt} didn't work, trying again…")
            with open(correction_log, "a") as f:
                f.write("Result: Still Failing\n")
                f.write(f"FAILED CODE:\n{new_code}\n")
            error_message = error_catcher(retry_result)

    if not fixed:
        report(f"Could not fix after {max_attempts} attempts")
        with open(correction_log, "a") as f:
            f.write(f"Final Result: {max_attempts} attempts failed\n")
        with open(log_report, "w") as f:
            f.write("qwen 2.5 crash report\n")
            f.write(f"Stdout:{result.stdout}\n")
            f.write(f"Stderr:{result.stderr}\n")
        return False

    return True


if __name__ == "__main__":
    execute_cad_scripts("ai_gen_script.py", "test run")