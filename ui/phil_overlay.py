"""
FILE: ui/phil_overlay.py

The top-level Tkinter window and state controller.

CHANGES vs previous version:
  1. _auto_resize() — measures the inner widget's required height and
     resizes the window to fit exactly, with a small padding.
     Called automatically from every state change via _schedule_resize().
     No more hardcoded pixel sizes scattered around the code.

  2. _spawn_command() now calls phil.show_thinking_state() on the
     main thread so the user sees visual feedback instantly, even
     before the AI starts running.

  3. Hard-coded self._resize(w, h) calls removed from every handler.
     The auto-resize takes care of it.

  4. Crash fix: set_status() in phil_widget.py is now safe to call
     from any state.  (Guard added there; nothing changes here.)

macOS / Tk 9 threading rules:
  - All Tkinter calls on main thread only.
  - Background threads → self.after(0, callback) for UI updates.
  - Mic/audio closed before after() fires.
"""

# changes v2

"""
FILE: ui/phil_overlay.py
 
CHANGES in this version:
  - _spawn_command() now shows an animated progress bar + live status text
    while the AI and FreeCAD runner are working.
  - status_callback is threaded through process_command → execute_cad_scripts
    so every stage ("Sending to AI…", "Self-correcting… attempt 1/3", etc.)
    updates the UI label in real time.
  - Animated bar pulses while processing; fills segment-by-segment on
    self-correction attempts so the user always knows something is happening.
  - No terminal output required by the user — DEBUG flag controls that.
"""

# v2 changes
"""
FILE: ui/phil_overlay.py
 
CHANGES in this version:
  - _spawn_command() now shows an animated progress bar + live status text
    while the AI and FreeCAD runner are working.
  - status_callback is threaded through process_command → execute_cad_scripts
    so every stage ("Sending to AI…", "Self-correcting… attempt 1/3", etc.)
    updates the UI label in real time.
  - Animated bar pulses while processing; fills segment-by-segment on
    self-correction attempts so the user always knows something is happening.
  - No terminal output required by the user — DEBUG flag controls that.
"""


import threading
import time
import sys
import json
from pathlib import Path
 
import customtkinter as ctk  # type: ignore
 
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
 
from ui.phil_widget import Visual_look_Phill
 
_W      = 400
_W_IDLE = 320
_PAD_H  = 50
 
# Set True during development to keep terminal logs
DEBUG = True
 
 
class Phil_Overlay(ctk.CTk):
 
    def __init__(self):
        super().__init__()
 
        self.is_ready        = False
        self._voice_active   = False
        self.processing_lock = threading.Lock()
 
        self._last_request = ""
        self._last_thumb   = None
 
        # ── loading bar state ─────────────────────────────────────────
        self._bar_animating  = False   # True while the pulse loop runs
        self._bar_progress   = 0.0    # 0.0 → 1.0
 
        # ── window setup ──────────────────────────────────────────────
        self.withdraw()
        self.title("Phil")
        self.attributes("-topmost", True)
        self.resizable(False, False)
 
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{_W_IDLE}x130+{(sw - _W_IDLE) // 2}+{sh - 200}")
 
        # ── main widget ───────────────────────────────────────────────
        self.phil = Visual_look_Phill(
            master=self,
            bg_color=ctk.ThemeManager.theme["CTk"]["fg_color"],
        )
        self.phil.pack(expand=True, fill="both")
 
        # ── loading bar widgets (hidden until processing starts) ──────
        self._build_loading_bar()
 
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(300, self._show)
 
    # ── loading bar construction ───────────────────────────────────────
 
    def _build_loading_bar(self):
        """
        Create a slim progress bar + status label that live BELOW the
        phil widget.  They are hidden by default and shown only during
        processing.
        """
        # Container frame — sits below self.phil
        self._bar_frame = ctk.CTkFrame(self, height=36, fg_color="transparent")
        # Don't pack yet — shown in _start_loading()
 
        self._status_label = ctk.CTkLabel(
            self._bar_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
            anchor="w",
        )
        self._status_label.pack(side="top", fill="x", padx=14, pady=(4, 0))
 
        self._progress_bar = ctk.CTkProgressBar(
            self._bar_frame,
            height=4,
            corner_radius=2,
            progress_color=("#5B9CF6", "#4A86E8"),   # calm blue
            fg_color=("gray85", "gray25"),
        )
        self._progress_bar.set(0)
        self._progress_bar.pack(side="top", fill="x", padx=14, pady=(2, 6))
 
    # ── loading bar control (called from main thread only) ────────────
 
    def _start_loading(self, initial_text: str = "Thinking…"):
        """Show the bar and start the pulse animation."""
        self._bar_progress  = 0.05   # small initial fill so it's not empty
        self._bar_animating = True
        self._progress_bar.set(self._bar_progress)
        self._status_label.configure(text=initial_text)
 
        # Pack the bar frame below phil widget if not already visible
        if not self._bar_frame.winfo_ismapped():
            self._bar_frame.pack(side="top", fill="x")
 
        self._pulse_bar()
 
    def _pulse_bar(self):
        """
        Slowly creep the bar forward while we're waiting, so it always
        looks alive.  Stops at 0.85 — the final jump to 1.0 happens
        only on actual success.
        """
        if not self._bar_animating:
            return
        if self._bar_progress < 0.85:
            self._bar_progress += 0.012
            self._progress_bar.set(self._bar_progress)
        self.after(120, self._pulse_bar)
 
    def _update_status(self, message: str):
        """
        Called by the status_callback from background threads via after().
        Updates:
          1. The bottom loading bar label + progress bump
          2. The thinking state label + pulse ring color (via phil widget)
        """
        # Update loading bar label
        self._status_label.configure(text=message)
 
        # Small bump so the bar visibly reacts to each stage change
        bump = 0.06
        self._bar_progress = min(self._bar_progress + bump, 0.88)
        self._progress_bar.set(self._bar_progress)
 
        # Route to thinking label + ring color if we're in thinking state
        if self.phil._current_state == "thinking":
            self.phil.update_thinking_label(message)
 
        if DEBUG:
            print(f"[Phil status] {message}")
 
    def _stop_loading(self, success: bool = True):
        """Fill bar to 100 % on success, turn red on failure, then hide."""
        self._bar_animating = False
 
        if success:
            self._progress_bar.configure(progress_color=("#34C759", "#28A745"))
            self._progress_bar.set(1.0)
            self._status_label.configure(text="Done! ✓")
        else:
            self._progress_bar.configure(progress_color=("#FF3B30", "#DC3545"))
            self._progress_bar.set(self._bar_progress)
            self._status_label.configure(text="Failed after 3 attempts")
 
        # Reset bar colour and hide after a short pause
        self.after(1800, self._hide_loading)
 
    def _hide_loading(self):
        self._bar_frame.pack_forget()
        # Reset colour back to blue for next run
        self._progress_bar.configure(progress_color=("#5B9CF6", "#4A86E8"))
        self._progress_bar.set(0)
        self._status_label.configure(text="")
        self._bar_progress  = 0.0
        self._bar_animating = False
 
    # ── startup ───────────────────────────────────────────────────────
 
    def _show(self):
        self.deiconify()
        self.lift()
        self.is_ready = True
        print("[Phil] Ready!")
 
    # ── auto-resize ───────────────────────────────────────────────────
 
    def _auto_resize(self):
        self.update_idletasks()
        state = self.phil._current_state
        width = _W_IDLE if state == "idle" else _W
        req_h = self.phil.winfo_reqheight()
 
        # Add extra room when the loading bar is visible
        bar_h = 40 if self._bar_frame.winfo_ismapped() else 0
        height = req_h + _PAD_H + bar_h
 
        self.geometry(f"{width}x{int(height)}+{self.winfo_x()}+{self.winfo_y()}")
 
    def _resize(self, w: int, h: int):
        self.geometry(f"{w}x{h}+{self.winfo_x()}+{self.winfo_y()}")
 
    # ── button handlers ───────────────────────────────────────────────
 
    def on_voice_click(self):
        if self._voice_active:
            self._voice_active = False
            self.phil.set_voice_active(False)
            self.phil.set_status("Ready To Build", "normal")
            return
 
        self._voice_active = True
        self.phil.set_voice_active(True)
        self.phil.set_status("Listening…", "thinking")
 
        threading.Thread(
            target=self._voice_task, daemon=True, name="VoiceTask"
        ).start()
 
    def on_text_click(self):
        if self.phil.entry_frame.winfo_ismapped():
            self.phil.hide_text_entry()
        else:
            self.phil.show_text_entry()
 
    def on_text_submit(self, text: str):
        text = text.strip()
        if not text:
            return
        self.phil.entry.delete(0, "end")
        self.phil.hide_text_entry()
        self._spawn_command(text)
 
    def execute_command_flow(self, user_input: str):
        self._spawn_command(user_input)
 
    # ── voice task ────────────────────────────────────────────────────
 
    def _voice_task(self):
        result = None
        try:
            import speech_recognition as sr  # type: ignore
            rec = sr.Recognizer()
            rec.pause_threshold          = 0.8
            rec.dynamic_energy_threshold = True
 
            with sr.Microphone() as source:
                rec.adjust_for_ambient_noise(source, duration=0.3)
                print("[Voice] Listening...")
                audio = rec.listen(source, timeout=8, phrase_time_limit=15)
 
            result = rec.recognize_google(audio)
            print(f"[Voice] Heard: {result}")
 
        except Exception as e:
            print(f"[Voice] {e}")
 
        self.after(0, lambda: self._finish_voice(result))
 
    def _finish_voice(self, text):
        self._voice_active = False
        self.phil.set_voice_active(False)
        if text:
            self._spawn_command(text)
        else:
            self.phil.set_status("Didn't catch that", "danger")
            self.after(2000, lambda: self.phil.set_status("Ready To Build", "normal"))
 
    # ── command processing ────────────────────────────────────────────
 
    def _spawn_command(self, user_input: str):
        """
        Switch to thinking state, show the loading bar, then start the
        background AI + FreeCAD thread.
        """
        self._last_request = user_input
 
        self.phil.show_thinking_state("Thinking…")
        self.phil.set_status("Thinking…", "thinking")
 
        # Show loading bar immediately
        self._start_loading("Sending to AI…")
        self._auto_resize()
 
        threading.Thread(
            target=self._run_command, args=(user_input,),
            daemon=True, name="CmdThread",
        ).start()
 
    def _run_command(self, user_input: str):
        """
        Background thread.  Every status update from runner/bridge calls
        self.after(0, ...) to safely touch the UI from the main thread.
        """
        def status_callback(message: str):
            # Always dispatch to main thread
            self.after(0, lambda m=message: self._update_status(m))
 
        with self.processing_lock:
            success = False
            try:
                from voice_input.command_bridge import process_command
                success = process_command(user_input, status_callback=status_callback)
 
                if success:
                    from ui.thumbnail import generate_snippet
                    thumb = generate_snippet()
                    self.after(0, lambda: self._finish_success(thumb, user_input))
                else:
                    self.after(0, lambda: self._finish_failure("Command failed"))
 
            except Exception as e:
                print(f"[Phil] Error: {e}")
                self.after(0, lambda: self._finish_failure(str(e)))
 
    def _finish_success(self, thumb, user_input):
        self._stop_loading(success=True)
        # Small delay so user sees the green "Done!" before preview appears
        self.after(600, lambda: self._show_preview(thumb, user_input))
 
    def _finish_failure(self, msg: str):
        self._stop_loading(success=False)
        self.after(2000, lambda: self._show_error(msg))
 
    def _show_error(self, msg: str = "Error!"):
        self.phil.set_status(msg, "danger")
        self.after(2000, self._reset_to_idle)
 
    def _reset_to_idle(self):
        self.phil.show_idle_state()
        self.phil.set_status("Ready To Build", "normal")
 
    # ── preview state ─────────────────────────────────────────────────
 
    def _show_preview(self, thumb_path, user_request):
        self._last_thumb   = thumb_path
        self._last_request = user_request
        preview_text = user_request
        try:
            from voice_input.Keys.config import ai_gen_folder
            spec_path = ai_gen_folder / "last_spec.json"
            if spec_path.exists():
                data = json.loads(spec_path.read_text())
                preview_text = data.get("description") or data.get("request") or user_request
        except Exception:
            preview_text = user_request
 
        self.phil.show_preview_state(
            thumb_path=thumb_path,
            prompt_text=preview_text,
            on_accept=self._on_accept,
            on_modify=self._on_modify,
            on_script=self._on_script,
        )
 
    def _on_accept(self):
        self.phil.show_export_state(
            on_freecad=self._export_freecad,
            on_blender=self._export_blender,
            on_back=self._back_to_idle,
        )
 
    def _on_modify(self):
        self.phil.show_modify_state(on_submit=self._on_modify_submit)
 
    def _on_modify_submit(self, new_text: str):
        new_text = new_text.strip()
        if not new_text:
            return
        self.phil.hide_modify_entry()
        self._spawn_command(new_text)
 
    def _on_script(self):
        from voice_input.Keys.config import ai_gen_script
        try:
            code = open(ai_gen_script).read()
        except Exception:
            code = "# Script not found."
        last_req   = self._last_request
        last_thumb = self._last_thumb
        self.phil.show_script_panel(
            code=code,
            on_back=lambda: self._show_preview(last_thumb, last_req),
        )
 
    # ── export handlers ───────────────────────────────────────────────
 
    def _export_freecad(self, mode: str = "save"):
        from ui.exporter import export_to_freecad
        threading.Thread(target=export_to_freecad, args=(mode,), daemon=True).start()
 
    def _export_blender(self, mode: str = "save"):
        from ui.exporter import export_to_blender
        threading.Thread(target=export_to_blender, args=(mode,), daemon=True).start()
 
    def _back_to_idle(self):
        self.phil.show_idle_state()
 
    # ── shutdown ──────────────────────────────────────────────────────
 
    def on_close(self):
        self.quit()
        self.destroy()
 