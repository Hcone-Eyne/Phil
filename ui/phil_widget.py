"""
FILE: ui/phil_widget.py

Visual states: idle, thinking, preview, modify, export, script panel.

Design language: VS Code sidebar extension — dark, minimal, icon-forward.

KEY FIX (Modify Further crash):
  set_status() now guards with winfo_exists() before calling .configure()
  on any widget.  When show_preview_state() calls _clear(), all idle
  widgets (including status_label) are destroyed.  Without the guard,
  the next call to set_status() hits a dead Tk widget → TclError.

AUTO-RESIZE:
  Every state method calls self._master._auto_resize() at the end via
  self.after(10, ...).  The overlay measures its own winfo_reqheight()
  after the layout settles and adjusts the window height accordingly.
  This means NO manual pixel heights are needed in the overlay.
"""


# v2 changes
"""
FILE: ui/phil_widget.py
 
Visual states: idle, thinking, preview, modify, export, script panel.
 
Design language: VS Code sidebar extension — dark, minimal, icon-forward.
 
ANIMATIONS (new):
  - Breathing pulse ring on thinking state — tk.Canvas circle that slowly
    expands/contracts. Color matches stage:
      amber  (#FAB387) = thinking / generating
      green  (#A6E3A1) = fixed / success
      red    (#F38BA8) = error / failed
  - Fade transitions between states — window dissolves out (150ms),
    rebuilds, dissolves back in (150ms). Apple-style: things dissolve,
    they don't snap.
 
KEY FIX (Modify Further crash):
  set_status() guards with winfo_exists() before calling .configure()
  on any widget. When show_preview_state() calls _clear(), all idle
  widgets (including status_label) are destroyed. Without the guard,
  the next call to set_status() hits a dead Tk widget → TclError.
 
AUTO-RESIZE:
  Every state method calls self._master._auto_resize() at the end via
  self.after(10, ...). The overlay measures its own winfo_reqheight()
  after the layout settles and adjusts the window height accordingly.
"""
 


import tkinter as tk
import math
import customtkinter as ctk  # type: ignore
from PIL import Image         # type: ignore


# ── Design tokens ──────────────────────────────────────────────────────────────
class phil_theme:
    bg          = "#18181B"
    pill_bg     = "#27272A"
    surface     = "#3F3F46"
    surface2    = "#FAFAFA"
    border_idle = "#3D3D5C"
    border_focus= "#6366F1"
    text_main   = "#CDD6F4"
    text_dim    = "#7F849C"
    text_accent = "#89B4FA"

    btn_voice   = "#6366F1"
    btn_text    = "#0EA5E9"
    btn_hover_v = "#4F46E5"
    btn_hover_t = "#0284C7"
    btn_green   = "#40A02B"
    btn_hover_g = "#2A8012"

    safe        = "#A6E3A1"
    danger      = "#F38BA8"
    thinking    = "#FAB387"

    btn_accept  = "#6366F1"
    radius_card = 12
    radius_btn  = 8

    # Pulse ring colors per stage
    pulse_thinking = "#FAB387"   # amber — generating / correcting
    pulse_success  = "#A6E3A1"   # green — fixed / done
    pulse_error    = "#F38BA8"   # red   — failed


# ── Breathing Pulse Ring ───────────────────────────────────────────────────────

class PulseRing(tk.Canvas):
    """
    A breathing circle drawn on a transparent Canvas.
    Mimics the Siri / Apple Intelligence ambient glow.

    The ring slowly expands and contracts using a sine wave so it feels
    organic — never mechanical. Color can be updated mid-animation to
    reflect the current processing stage.
    """

    _RADIUS_MIN = 28    # inner breath (smallest)
    _RADIUS_MAX = 42    # outer breath (largest)
    _GLOW_EXTRA = 10    # soft outer glow ring radius offset
    _TICK_MS    = 32    # ~30 fps — smooth without hogging CPU
    _SPEED      = 0.04  # radians per tick — controls breath rate

    def __init__(self, parent, color: str = phil_theme.pulse_thinking, **kwargs):
        size = (self._RADIUS_MAX + self._GLOW_EXTRA + 4) * 2
        super().__init__(
            parent,
            width=size, height=size,
            bg=phil_theme.pill_bg,
            highlightthickness=0,
            **kwargs,
        )
        self._color    = color
        self._phase    = 0.0       # sine wave position
        self._running  = False
        self._glow_id  = None
        self._ring_id  = None
        self._dot_id   = None
        self._size     = size
        self._draw()

    # ── public API ─────────────────────────────────────────────────────

    def start(self):
        """Begin the breathing animation."""
        self._running = True
        self._tick()

    def stop(self):
        """Freeze the ring in place."""
        self._running = False

    def set_color(self, color: str):
        """Hot-swap the ring color mid-animation (e.g. amber → green on fix)."""
        self._color = color
        self._draw()

    # ── internal ───────────────────────────────────────────────────────

    def _tick(self):
        if not self._running:
            return
        self._phase += self._SPEED
        self._draw()
        self.after(self._TICK_MS, self._tick)

    def _draw(self):
        """Redraw all three layers: outer glow, ring, centre dot."""
        cx = cy = self._size / 2

        # t goes 0→1→0 (sine breath)
        t = (math.sin(self._phase) + 1) / 2
        r = self._RADIUS_MIN + t * (self._RADIUS_MAX - self._RADIUS_MIN)

        # ── outer glow (faint, large) ─────────────────────────────────
        gr = r + self._GLOW_EXTRA
        glow_color = self._dim_color(self._color, 0.18)
        self._replace(
            self._glow_id,
            self.create_oval(cx - gr, cy - gr, cx + gr, cy + gr,
                             outline=glow_color, width=6, fill=""),
        )
        self._glow_id = self.find_withtag("glow_tag") or self._glow_id

        # ── main ring ─────────────────────────────────────────────────
        ring_color = self._dim_color(self._color, 0.55 + t * 0.45)
        if self._ring_id:
            self.coords(self._ring_id,
                        cx - r, cy - r, cx + r, cy + r)
            self.itemconfig(self._ring_id, outline=ring_color, width=2)
        else:
            self._ring_id = self.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline=ring_color, width=2, fill="",
            )

        # ── centre dot ────────────────────────────────────────────────
        dr = 6
        dot_color = self._dim_color(self._color, 0.7 + t * 0.3)
        if self._dot_id:
            self.coords(self._dot_id,
                        cx - dr, cy - dr, cx + dr, cy + dr)
            self.itemconfig(self._dot_id, fill=dot_color, outline="")
        else:
            self._dot_id = self.create_oval(
                cx - dr, cy - dr, cx + dr, cy + dr,
                fill=dot_color, outline="",
            )

    def _replace(self, old_id, new_id):
        if old_id:
            self.delete(old_id)

    @staticmethod
    def _dim_color(hex_color: str, alpha: float) -> str:
        """
        Blend hex_color toward the background (#27272A) by alpha.
        alpha=1.0 → full color, alpha=0.0 → background.
        Pure Python — no extra libs needed.
        """
        bg = (0x27, 0x27, 0x2A)
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        r2 = int(bg[0] + (r - bg[0]) * alpha)
        g2 = int(bg[1] + (g - bg[1]) * alpha)
        b2 = int(bg[2] + (b - bg[2]) * alpha)
        return f"#{r2:02x}{g2:02x}{b2:02x}"


# ── Main Widget ────────────────────────────────────────────────────────────────

class Visual_look_Phill(ctk.CTkFrame):

    # Fade steps and duration (Apple feel: fast out, fast in)
    _FADE_STEPS    = 8
    _FADE_TICK_MS  = 18   # 8 × 18ms ≈ 144ms per fade direction

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=phil_theme.pill_bg,
            corner_radius=20,
            border_width=1,
            border_color=phil_theme.border_idle,
            **kwargs,
        )
        self._master        = master
        self._current_state = "idle"
        self._pulse_ring    = None   # active PulseRing instance (or None)
        self._fading        = False  # guard: don't stack fade calls
        self._build_idle_state()

    # ══════════════════════════════════════════════════════════════════════════
    # FADE ENGINE
    # Apple rule: content dissolves out, new content dissolves in.
    # We animate the top-level window alpha so everything fades together.
    # ══════════════════════════════════════════════════════════════════════════

    def _fade_transition(self, build_fn, *args, **kwargs):
        """
        Fade out → call build_fn(*args, **kwargs) → fade in.
        Safe to call from any state; queues behind any running fade.
        """
        if self._fading:
            # Already mid-transition — just rebuild immediately
            self._stop_pulse()
            self._clear()
            build_fn(*args, **kwargs)
            return

        self._fading = True
        win = self.winfo_toplevel()
        self._fade_out(win, self._FADE_STEPS, build_fn, args, kwargs)

    def _fade_out(self, win, steps_left, build_fn, args, kwargs):
        if steps_left <= 0:
            # Bottom of fade — rebuild content
            self._stop_pulse()
            self._clear()
            build_fn(*args, **kwargs)
            self.after(10, lambda: self._fade_in(win, self._FADE_STEPS))
            return
        alpha = steps_left / self._FADE_STEPS
        try:
            win.attributes("-alpha", alpha)
        except Exception:
            pass
        self.after(self._FADE_TICK_MS,
                   lambda: self._fade_out(win, steps_left - 1, build_fn, args, kwargs))

    def _fade_in(self, win, steps_left):
        total = self._FADE_STEPS
        if steps_left <= 0:
            try:
                win.attributes("-alpha", 1.0)
            except Exception:
                pass
            self._fading = False
            return
        alpha = (total - steps_left + 1) / total
        try:
            win.attributes("-alpha", alpha)
        except Exception:
            pass
        self.after(self._FADE_TICK_MS,
                   lambda: self._fade_in(win, steps_left - 1))

    # ══════════════════════════════════════════════════════════════════════════
    # PULSE RING HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _start_pulse(self, color: str = phil_theme.pulse_thinking):
        """Create and start a PulseRing. Only one can exist at a time."""
        self._stop_pulse()
        self._pulse_ring = PulseRing(self, color=color)
        self._pulse_ring.pack(pady=(10, 4))
        self._pulse_ring.start()

    def _stop_pulse(self):
        """Stop and destroy the current PulseRing if one exists."""
        if self._pulse_ring is not None:
            try:
                self._pulse_ring.stop()
                if self._pulse_ring.winfo_exists():
                    self._pulse_ring.destroy()
            except Exception:
                pass
            self._pulse_ring = None

    def update_pulse_color(self, color: str):
        """
        Hot-swap pulse color mid-animation.
        Called from phil_overlay when a status update signals a stage change.
        e.g. 'Fixed! ✓' → green, 'Could not fix' → red.
        """
        if self._pulse_ring is not None:
            try:
                self._pulse_ring.set_color(color)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════════════
    # IDLE STATE
    # ══════════════════════════════════════════════════════════════════════════

    def _build_idle_state(self):
        self._current_state = "idle"

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 6))

        dot = ctk.CTkLabel(
            header, text="●",
            text_color=phil_theme.btn_green,
            font=("Inter", 9),
            fg_color="transparent",
        )
        dot.pack(side="left", padx=(0, 5))

        self.status_label = ctk.CTkLabel(
            header, text="READY TO BUILD",
            text_color=phil_theme.text_main,
            font=("Inter", 11, "bold"),
            fg_color="transparent",
        )
        self.status_label.pack(side="left")

        div = ctk.CTkFrame(self, fg_color=phil_theme.border_idle, height=1)
        div.pack(fill="x", padx=14, pady=(0, 10))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=14, pady=(0, 12))

        self.voice_btn = ctk.CTkButton(
            btn_row, text="🎙  Voice",
            width=130, height=34, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.btn_voice,
            hover_color=phil_theme.btn_hover_v,
            text_color="#FFFFFF",
            font=("Inter", 12, "bold"),
            command=self.master.on_voice_click,
        )
        self.voice_btn.pack(side="left", padx=(0, 8))

        self.text_btn = ctk.CTkButton(
            btn_row, text="✏  Text",
            width=130, height=34, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.btn_text,
            hover_color=phil_theme.btn_hover_t,
            text_color="#FFFFFF",
            font=("Inter", 12, "bold"),
            command=self.master.on_text_click,
        )
        self.text_btn.pack(side="left")

        self.entry_frame = ctk.CTkFrame(self, fg_color="transparent")

        self.entry = ctk.CTkEntry(
            self.entry_frame,
            placeholder_text="Type your command…",
            width=235, height=34,
            fg_color=phil_theme.surface,
            text_color=phil_theme.text_main,
            placeholder_text_color=phil_theme.text_dim,
            border_color=phil_theme.btn_text,
            border_width=1,
            font=("Inter", 12),
            corner_radius=phil_theme.radius_btn,
        )
        self.entry.pack(side="left", padx=(0, 6))
        self.entry.bind("<Return>", lambda e: self.master.on_text_submit(self.entry.get()))

        ctk.CTkButton(
            self.entry_frame, text="→",
            width=34, height=34, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.btn_text,
            hover_color=phil_theme.btn_hover_t,
            text_color="#FFFFFF",
            font=("Inter", 15, "bold"),
            command=lambda: self.master.on_text_submit(self.entry.get()),
        ).pack(side="left")

        self._schedule_resize()

    # ══════════════════════════════════════════════════════════════════════════
    # THINKING STATE — breathing pulse ring + live status label
    # ══════════════════════════════════════════════════════════════════════════

    def _build_thinking_state(self, message: str = "Thinking…"):
        self._current_state = "thinking"

        # Breathing ring — amber while generating
        self._start_pulse(color=phil_theme.pulse_thinking)

        # Status text below the ring
        self._thinking_label = ctk.CTkLabel(
            self, text=message,
            text_color=phil_theme.thinking,
            font=("Inter", 12, "bold"),
            fg_color="transparent",
        )
        self._thinking_label.pack(pady=(2, 16), padx=16)

        self.configure(border_color=phil_theme.thinking)
        self._schedule_resize()

    def show_thinking_state(self, message: str = "Thinking…"):
        """Public entry point — fades in the thinking state."""
        self._fade_transition(self._build_thinking_state, message)

    def update_thinking_label(self, message: str):
        """
        Update the status text under the pulse ring without rebuilding the state.
        Called from phil_overlay's status_callback so the label tracks every stage.
        Also hot-swaps the ring color based on the message content.
        """
        # Update label if it exists
        if hasattr(self, "_thinking_label"):
            try:
                if self._thinking_label.winfo_exists():
                    self._thinking_label.configure(text=message)
            except Exception:
                pass

        # Color logic — read the message to know the stage
        msg_lower = message.lower()
        if any(k in msg_lower for k in ("fix", "done", "✓", "success")):
            self.update_pulse_color(phil_theme.pulse_success)
            self.configure(border_color=phil_theme.safe)
        elif any(k in msg_lower for k in ("fail", "error", "could not", "unavailable")):
            self.update_pulse_color(phil_theme.pulse_error)
            self.configure(border_color=phil_theme.danger)
        else:
            # Still working — keep amber
            self.update_pulse_color(phil_theme.pulse_thinking)
            self.configure(border_color=phil_theme.thinking)

    # ══════════════════════════════════════════════════════════════════════════
    # PREVIEW STATE
    # ══════════════════════════════════════════════════════════════════════════

    def _build_preview_state(self, thumb_path, prompt_text, on_accept, on_modify, on_script):
        self._current_state = "preview"

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(
            hdr, text="3D Preview",
            text_color=phil_theme.text_accent,
            font=("Inter", 11, "bold"),
            fg_color="transparent",
        ).pack(side="left")
        ctk.CTkLabel(
            hdr, text="click image to view script →",
            text_color=phil_theme.text_dim,
            font=("Inter", 9),
            fg_color="transparent",
        ).pack(side="right")

        thumb_frame = ctk.CTkFrame(self, fg_color=phil_theme.surface2, corner_radius=10)
        thumb_frame.pack(pady=(6, 0), padx=14, fill="x")

        if thumb_path and thumb_path.exists():
            img = Image.open(thumb_path)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(340, 190))
            thumb_label = ctk.CTkLabel(thumb_frame, image=ctk_img, text="")
        else:
            thumb_label = ctk.CTkLabel(
                thumb_frame,
                text="⬜  3D Preview Unavailable",
                text_color=phil_theme.text_dim,
                font=("Inter", 12),
                fg_color="transparent",
                height=196,
            )

        thumb_label.pack(padx=6, pady=6)

        script_hint = ctk.CTkLabel(
            thumb_frame, text="🔍  View Script",
            text_color="#FFFFFF",
            fg_color=phil_theme.surface,
            font=("Inter", 10, "bold"),
            corner_radius=6,
        )
        thumb_label.bind("<Enter>", lambda e: script_hint.place(relx=0.5, rely=0.9, anchor="center"))
        thumb_label.bind("<Leave>", lambda e: script_hint.place_forget())
        thumb_label.bind("<Button-1>", lambda e: on_script())
        thumb_label.configure(cursor="hand2")

        prompt_chip = ctk.CTkFrame(self, fg_color=phil_theme.surface, corner_radius=8)
        prompt_chip.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            prompt_chip,
            text=f'"{prompt_text}"',
            text_color=phil_theme.text_dim,
            font=("Inter", 10, "italic"),
            wraplength=340,
            justify="left",
            fg_color="transparent",
        ).pack(padx=10, pady=6, anchor="w")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(10, 14), padx=14)

        ctk.CTkButton(
            btn_row, text="✔  Accept",
            width=160, height=36, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.btn_green,
            hover_color=phil_theme.btn_hover_g,
            text_color="#FFFFFF",
            font=("Inter", 12, "bold"),
            command=on_accept,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="✏  Modify",
            width=160, height=36, corner_radius=phil_theme.radius_btn,
            fg_color="transparent",
            border_width=1,
            border_color=phil_theme.border_idle,
            text_color=phil_theme.text_main,
            font=("Inter", 12),
            command=on_modify,
        ).pack(side="left")

        self._schedule_resize()

    def show_preview_state(self, thumb_path, prompt_text, on_accept, on_modify, on_script):
        self._fade_transition(
            self._build_preview_state,
            thumb_path, prompt_text, on_accept, on_modify, on_script,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # MODIFY STATE
    # ══════════════════════════════════════════════════════════════════════════

    def show_modify_state(self, on_submit):
        """Appends a styled input row below the existing preview content."""
        self._current_state = "modify"

        div = ctk.CTkFrame(self, fg_color=phil_theme.border_idle, height=1)
        div.pack(fill="x", padx=14, pady=(4, 8))

        ctk.CTkLabel(
            self, text="Describe your modification",
            text_color=phil_theme.text_dim,
            font=("Inter", 10),
            fg_color="transparent",
        ).pack(anchor="w", padx=16)

        self.modify_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.modify_frame.pack(pady=(4, 14), padx=14, fill="x")

        self.modify_entry = ctk.CTkEntry(
            self.modify_frame,
            placeholder_text="e.g. make it taller by 10mm…",
            height=36,
            fg_color=phil_theme.surface,
            text_color=phil_theme.text_main,
            placeholder_text_color=phil_theme.text_dim,
            border_color=phil_theme.btn_text,
            border_width=1,
            font=("Inter", 12),
            corner_radius=phil_theme.radius_btn,
        )
        self.modify_entry.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.modify_entry.bind("<Return>", lambda e: on_submit(self.modify_entry.get()))
        self.modify_entry.focus()

        ctk.CTkButton(
            self.modify_frame, text="→",
            width=36, height=36, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.btn_text,
            hover_color=phil_theme.btn_hover_t,
            text_color="#FFFFFF",
            font=("Inter", 15, "bold"),
            command=lambda: on_submit(self.modify_entry.get()),
        ).pack(side="left")

        self._schedule_resize()

    def hide_modify_entry(self):
        if hasattr(self, "modify_frame") and self.modify_frame.winfo_exists():
            self.modify_frame.destroy()

    # ══════════════════════════════════════════════════════════════════════════
    # EXPORT STATE
    # ══════════════════════════════════════════════════════════════════════════

    def _build_export_state(self, on_freecad, on_blender, on_back):
        self._current_state = "export"

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(
            hdr, text="Export Model",
            text_color=phil_theme.text_main,
            font=("Inter", 13, "bold"),
            fg_color="transparent",
        ).pack(side="left")

        ctk.CTkFrame(self, fg_color=phil_theme.border_idle, height=1).pack(
            fill="x", padx=14, pady=(8, 10)
        )

        ctk.CTkLabel(
            self, text="Choose format and action",
            text_color=phil_theme.text_dim,
            font=("Inter", 10),
            fg_color="transparent",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        def _card(icon, name, fmt, save_cb, open_cb, reveal_cb):
            card = ctk.CTkFrame(self, fg_color=phil_theme.surface, corner_radius=10)
            card.pack(padx=14, pady=(0, 8), fill="x")

            title_row = ctk.CTkFrame(card, fg_color="transparent")
            title_row.pack(fill="x", padx=10, pady=(8, 4))

            ctk.CTkLabel(
                title_row, text=icon,
                font=("Inter", 16),
                fg_color="transparent",
                text_color=phil_theme.text_main,
            ).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(
                title_row, text=name,
                font=("Inter", 12, "bold"),
                text_color=phil_theme.text_main,
                fg_color="transparent",
            ).pack(side="left")

            ctk.CTkLabel(
                title_row, text=fmt,
                font=("Inter", 10),
                text_color=phil_theme.text_dim,
                fg_color="transparent",
            ).pack(side="left", padx=(6, 0))

            btn_row = ctk.CTkFrame(card, fg_color="transparent")
            btn_row.pack(fill="x", padx=10, pady=(0, 8))

            ctk.CTkButton(
                btn_row, text="💾 Save to…",
                height=28, corner_radius=phil_theme.radius_btn,
                fg_color=phil_theme.btn_accept,
                hover_color=phil_theme.btn_hover_v,
                text_color="#FFFFFF",
                font=("Inter", 11, "bold"),
                command=save_cb,
            ).pack(side="left", padx=(0, 5))

            ctk.CTkButton(
                btn_row, text="🚀 Open in App",
                height=28, corner_radius=phil_theme.radius_btn,
                fg_color="#1D4ED8",
                hover_color="#1E3A8A",
                text_color="#FFFFFF",
                font=("Inter", 11),
                command=open_cb,
            ).pack(side="left", padx=(0, 5))

            ctk.CTkButton(
                btn_row, text="📂 Reveal",
                height=28, corner_radius=phil_theme.radius_btn,
                fg_color="transparent",
                border_width=1,
                border_color=phil_theme.border_idle,
                text_color=phil_theme.text_dim,
                font=("Inter", 11),
                command=reveal_cb,
            ).pack(side="left")

        _card(
            "🟠", "FreeCAD", ".step",
            save_cb=lambda: on_freecad("save"),
            open_cb=lambda: on_freecad("import"),
            reveal_cb=lambda: on_freecad("reveal"),
        )
        _card(
            "🔵", "Blender", ".obj",
            save_cb=lambda: on_blender("save"),
            open_cb=lambda: on_blender("import"),
            reveal_cb=lambda: on_blender("reveal"),
        )

        ctk.CTkButton(
            self, text="← Back to Idle",
            height=30, corner_radius=phil_theme.radius_btn,
            fg_color="transparent",
            border_width=1,
            border_color=phil_theme.border_idle,
            text_color=phil_theme.text_dim,
            font=("Inter", 11),
            command=on_back,
        ).pack(pady=(0, 14), padx=14, fill="x")

        self._schedule_resize()

    def show_export_state(self, on_freecad, on_blender, on_back):
        self._fade_transition(self._build_export_state, on_freecad, on_blender, on_back)

    # ══════════════════════════════════════════════════════════════════════════
    # SCRIPT PANEL
    # ══════════════════════════════════════════════════════════════════════════

    def _build_script_panel(self, code: str, on_back=None):
        self._current_state = "script"
        self._script_back   = on_back

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(
            hdr, text="Generated Script",
            text_color=phil_theme.text_accent,
            font=("Inter", 12, "bold"),
            fg_color="transparent",
        ).pack(side="left")

        ctk.CTkFrame(self, fg_color=phil_theme.border_idle, height=1).pack(
            fill="x", padx=14, pady=(8, 6)
        )

        code_box = ctk.CTkTextbox(
            self,
            height=300,
            fg_color="#0D0D1A",
            text_color="#9CDCFE",
            font=("JetBrains Mono", 11),
            corner_radius=8,
            border_width=1,
            border_color=phil_theme.border_idle,
        )
        code_box.pack(padx=14, pady=(0, 8), fill="both")
        code_box.insert("0.0", code)
        code_box.configure(state="disabled")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(0, 14), padx=14, fill="x")

        def _copy():
            self.clipboard_clear()
            self.clipboard_append(code)

        ctk.CTkButton(
            btn_row, text="📋  Copy",
            height=30, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.btn_text,
            hover_color=phil_theme.btn_hover_t,
            text_color="#FFFFFF",
            font=("Inter", 11),
            command=_copy,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="← Back",
            height=30, corner_radius=phil_theme.radius_btn,
            fg_color="transparent",
            border_width=1,
            border_color=phil_theme.border_idle,
            text_color=phil_theme.text_dim,
            font=("Inter", 11),
            command=lambda: self._script_back() if self._script_back else None,
        ).pack(side="left")

        self._schedule_resize()

    def show_script_panel(self, code: str, on_back=None):
        self._fade_transition(self._build_script_panel, code, on_back)

    # ══════════════════════════════════════════════════════════════════════════
    # IDLE RESTORE
    # ══════════════════════════════════════════════════════════════════════════

    def show_idle_state(self):
        self._fade_transition(self._build_idle_state)

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _clear(self):
        """Destroy all child widgets."""
        for w in self.winfo_children():
            w.destroy()
        self._pulse_ring = None  # cleared by destroy, just null the ref

    def _schedule_resize(self):
        self.after(10, self._master._auto_resize)

    def set_status(self, message: str, state: str = "normal"):
        """
        Update status label + border. Guards against destroyed widgets.
        Also routes to update_thinking_label when in thinking state
        so the pulse ring color updates live.
        """
        if self._current_state == "thinking":
            self.update_thinking_label(message)
            return

        if hasattr(self, "status_label"):
            try:
                if self.status_label.winfo_exists():
                    self.status_label.configure(text=message.upper())
            except Exception:
                pass

        colors = {
            "safe":     phil_theme.safe,
            "danger":   phil_theme.danger,
            "thinking": phil_theme.thinking,
            "normal":   phil_theme.border_idle,
        }
        self.configure(border_color=colors.get(state, phil_theme.border_idle))

    def show_text_entry(self):
        self.entry_frame.pack(padx=14, pady=(0, 12))
        self.entry.delete(0, "end")
        self.entry.focus()
        self._schedule_resize()

    def hide_text_entry(self):
        self.entry_frame.pack_forget()
        self._schedule_resize()

    def set_voice_active(self, active: bool):
        if hasattr(self, "voice_btn") and self.voice_btn.winfo_exists():
            self.voice_btn.configure(
                fg_color=phil_theme.danger if active else phil_theme.btn_voice,
                text="⏹  Stop" if active else "🎙  Voice",
            )