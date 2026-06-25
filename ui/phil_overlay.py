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

import threading
import time
import sys
import json
from pathlib import Path

import customtkinter as ctk # type:ignore

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ui.phil_widget import Visual_look_Phill

# Minimum / maximum window widths
_W = 400           # fixed width for all states
_W_IDLE = 320      # narrower for idle pill
_PAD_H = 50        # extra vertical padding added to widget required height


class Phil_Overlay(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.is_ready        = False
        self._voice_active   = False
        self.processing_lock = threading.Lock()

        # cache for the most recent preview so Back buttons can restore it
        self._last_request   = ""
        self._last_thumb     = None

        # ── window setup ──────────────────────────────────────────────
        self.withdraw()

        # NOTE: overrideredirect(True) intentionally SKIPPED on Tk 9.0
        # — it causes the Tcl notifier crash on macOS.
        # self.overrideredirect(True)  ← DO NOT enable

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

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(300, self._show)

    # ── startup ───────────────────────────────────────────────────────

    def _show(self):
        self.deiconify()
        self.lift()
        self.is_ready = True
        print("[Phil] Ready!")

    # ── auto-resize ───────────────────────────────────────────────────

    def _auto_resize(self):
        """
        Measures the widget's required height after layout and resizes
        the window to fit.  Called via self.after(10, _auto_resize) from
        every state change in phil_widget.py.

        How it works:
          update_idletasks() flushes pending geometry calculations.
          winfo_reqheight() returns the height the widget *needs*.
          We add _PAD_H for the window title bar / border.
        """
        self.update_idletasks() # Flush current geometry
        state = self.phil._current_state
        width = _W_IDLE if state == "idle" else _W
        
        # Get required height
        req_h = self.phil.winfo_reqheight()
        
        # If in preview or script state, ensure a minimum height to prevent flickering
        height = req_h + _PAD_H
        
        self.geometry(f"{width}x{int(height)}+{self.winfo_x()}+{self.winfo_y()}")
    # ── resize helper (still useful for manual overrides if needed) ────

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

    # kept for any external callers
    def execute_command_flow(self, user_input: str):
        self._spawn_command(user_input)

    # ── voice task ────────────────────────────────────────────────────

    def _voice_task(self):
        """
        Opens mic, records ONE phrase, closes mic, then signals main thread.
        Mic is fully closed before self.after() fires so CoreAudio is done
        before Tcl's notifier processes the callback.
        """
        result = None
        try:
            import speech_recognition as sr # type:ignore
            rec = sr.Recognizer()
            rec.pause_threshold          = 0.8
            rec.dynamic_energy_threshold = True

            with sr.Microphone() as source:
                rec.adjust_for_ambient_noise(source, duration=0.3)
                print("[Voice] Listening...")
                audio = rec.listen(source, timeout=8, phrase_time_limit=15)
            # ← mic closed here; CoreAudio stream fully released

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
        Switch to thinking state immediately (user sees feedback now),
        then start the background AI + FreeCAD thread.
        """
        self._last_request = user_input

        # Show thinking state on main thread RIGHT NOW — before the thread starts
        self.phil.show_thinking_state("Thinking…")
        self.phil.set_status("Thinking…", "thinking")

        threading.Thread(
            target=self._run_command, args=(user_input,),
            daemon=True, name="CmdThread",
        ).start()

    def _run_command(self, user_input: str):
        with self.processing_lock:
            try:
                from voice_input.command_bridge import process_command
                success = process_command(user_input)

                if success:
                    from ui.thumbnail import generate_snippet
                    thumb = generate_snippet()
                    self.after(0, lambda: self._show_preview(thumb, user_input))
                else:
                    self.after(0, lambda: self._show_error("Command failed"))

            except Exception as e:
                print(f"[Phil] Error: {e}")
                self.after(0, lambda: self._show_error(str(e)))

    def _show_error(self, msg: str = "Error!"):
        self.phil.set_status(msg, "danger")
        self.after(2000, lambda: self._reset_to_idle())

    def _reset_to_idle(self):
        self.phil.show_idle_state()
        self.phil.set_status("Ready To Build", "normal")

    # ── preview state ─────────────────────────────────────────────────

    def _show_preview(self, thumb_path, user_request):
        """Switch Phil to preview state — show thumbnail + buttons."""
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
        """User clicked Accept — show export options."""
        self.phil.show_export_state(
            on_freecad=self._export_freecad,
            on_blender=self._export_blender,
            on_back=self._back_to_idle,
        )

    def _on_modify(self):
        """User clicked Modify — append input below preview content."""
        self.phil.show_modify_state(on_submit=self._on_modify_submit)

    def _on_modify_submit(self, new_text: str):
        """User submitted a modify prompt — run it."""
        new_text = new_text.strip()
        if not new_text:
            return
        self.phil.hide_modify_entry()
        # _spawn_command will switch to thinking state, safe regardless of
        # which state we're currently in (the crash is fixed in set_status)
        self._spawn_command(new_text)

    def _on_script(self):
        """User clicked the thumbnail — show generated script."""
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
        """mode = 'save' | 'import' | 'reveal'"""
        from ui.exporter import export_to_freecad
        threading.Thread(target=export_to_freecad, args=(mode,), daemon=True).start()

    def _export_blender(self, mode: str = "save"):
        """mode = 'save' | 'import' | 'reveal'"""
        from ui.exporter import export_to_blender
        threading.Thread(target=export_to_blender, args=(mode,), daemon=True).start()

    def _back_to_idle(self):
        self.phil.show_idle_state()

    def _switch_mode(self):
        """
        Called when user taps Switch Mode in settings.
        Closes Phil window and reopens setup screen so user
        can change between Local and API mode.
        After setup completes, Phil relaunches via on_complete callback.
        """
        self.quit()
        self.destroy()
        # Import here to avoid circular imports at module level
        from setup.setup_screen import SetupScreen
        import sys
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        def relaunch():
            from ui.phil_overlay import Phil_Overlay
            app = Phil_Overlay()
            app.mainloop()

        setup = SetupScreen(on_complete=relaunch)
        setup.mainloop()

    # ── shutdown ──────────────────────────────────────────────────────

    def on_close(self):
        self.quit()
        self.destroy()