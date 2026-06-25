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
 
 # v3 changes
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

# pyrefly: ignore [missing-import]
import customtkinter as ctk 
# pyrefly: ignore [missing-import]
from PIL import Image # type: ignore    


# ── Design tokens ─────────────────────────────────────────────────────────────
class phil_theme:
    bg          = "#18181B"      # deep navy — VS Code dark+
    pill_bg     = "#27272A"
    surface     = "#3F3F46"      # card / input background
    surface2    = "#FAFAFA"      # thumbnail background
    border_idle = "#3D3D5C"
    border_focus= "#6366F1"
    text_main   = "#CDD6F4"      # catppuccin text
    text_dim    = "#7F849C"      # catppuccin subtext
    text_accent = "#89B4FA"      # catppuccin blue

    btn_voice   = "#6366F1"      # indigo
    btn_text    = "#0EA5E9"      # sky
    btn_hover_v = "#4F46E5"
    btn_hover_t = "#0284C7"
    btn_green   = "#40A02B"      # accept / success
    btn_hover_g = "#2A8012"

    safe        = "#A6E3A1"
    danger      = "#F38BA8"
    thinking    = "#FAB387"

    btn_accept  = "#6366F1"
    radius_card = 12
    radius_btn  = 8


class Visual_look_Phill(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=phil_theme.pill_bg,
            corner_radius=20,
            border_width=1,
            border_color=phil_theme.border_idle,
            **kwargs
        )
        self._master = master
        # Track current active state name for auto-resize hints
        self._current_state = "idle"
        self._build_idle_state()

    # ══════════════════════════════════════════════════════════════════
    # IDLE STATE  — the default Phil you already know
    # ══════════════════════════════════════════════════════════════════

    def _build_idle_state(self):
        self._current_state = "idle"

        # ── status row ───────────────────────────────────────────────
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

        # ⚙ settings — top right, subtle so it doesn't distract
        ctk.CTkButton(
            header, text="⚙",
            width=28, height=28, corner_radius=6,
            fg_color="transparent",
            hover_color=phil_theme.surface,
            text_color=phil_theme.text_dim,
            font=("Inter", 13),
            command=self._show_settings_state,
        ).pack(side="right")

        # ── divider ──────────────────────────────────────────────────
        div = ctk.CTkFrame(self, fg_color=phil_theme.border_idle, height=1)
        div.pack(fill="x", padx=14, pady=(0, 10))

        # ── action buttons ───────────────────────────────────────────
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

        # ── text entry (hidden until Text is clicked) ─────────────────
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

    # ══════════════════════════════════════════════════════════════════
    # THINKING STATE — shown while AI is processing
    # ══════════════════════════════════════════════════════════════════

    def show_thinking_state(self, message: str = "Thinking…"):
        """Minimal state shown while the AI command runs."""
        self._clear()
        self._current_state = "thinking"

        ctk.CTkLabel(
            self, text="⏳  " + message,
            text_color=phil_theme.thinking,
            font=("Inter", 12, "bold"),
            fg_color="transparent",
        ).pack(pady=20, padx=16)

        self.configure(border_color=phil_theme.thinking)
        self._schedule_resize()

    # ══════════════════════════════════════════════════════════════════
    # PREVIEW STATE — thumbnail + prompt + accept/modify
    # ══════════════════════════════════════════════════════════════════

    def show_preview_state(self, thumb_path, prompt_text, on_accept, on_modify, on_script):
        self._clear()
        self._current_state = "preview"

        # ── header bar ────────────────────────────────────────────────
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

        # ── thumbnail ─────────────────────────────────────────────────
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

        # script hint overlay on hover
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

        # ── prompt chip ───────────────────────────────────────────────
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

        # ── action buttons ────────────────────────────────────────────
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

    # ══════════════════════════════════════════════════════════════════
    # MODIFY STATE — input appears below thumbnail
    # ══════════════════════════════════════════════════════════════════

    def show_modify_state(self, on_submit):
        """Appends a styled input row below the existing preview content."""
        self._current_state = "modify"

        # ── divider ──────────────────────────────────────────────────
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

    # ══════════════════════════════════════════════════════════════════
    # EXPORT STATE
    # ══════════════════════════════════════════════════════════════════

    def show_export_state(self, on_freecad, on_blender, on_back):
        self._clear()
        self._current_state = "export"

        # ── header ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(
            hdr, text="Export Model",
            text_color=phil_theme.text_main,
            font=("Inter", 13, "bold"),
            fg_color="transparent",
        ).pack(side="left")

        # ── divider ──────────────────────────────────────────────────
        ctk.CTkFrame(self, fg_color=phil_theme.border_idle, height=1).pack(
            fill="x", padx=14, pady=(8, 10)
        )

        ctk.CTkLabel(
            self, text="Choose format and action",
            text_color=phil_theme.text_dim,
            font=("Inter", 10),
            fg_color="transparent",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        # ── card builder ──────────────────────────────────────────────
        def _card(icon, name, fmt, save_cb, open_cb, reveal_cb):
            card = ctk.CTkFrame(self, fg_color=phil_theme.surface, corner_radius=10)
            card.pack(padx=14, pady=(0, 8), fill="x")

            # title row
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

            # button row
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

    # ══════════════════════════════════════════════════════════════════
    # SCRIPT PANEL
    # ══════════════════════════════════════════════════════════════════

    def show_script_panel(self, code: str, on_back=None):
        self._clear()
        self._current_state = "script"
        self._script_back = on_back

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

    # ══════════════════════════════════════════════════════════════════
    # SETTINGS STATE
    # ══════════════════════════════════════════════════════════════════

    def _show_settings_state(self):
        self._fade_transition(self._build_settings_state)

    def _build_settings_state(self):
        self._current_state = "settings"

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(
            hdr, text="⚙  Settings",
            text_color=phil_theme.text_main,
            font=("Inter", 13, "bold"),
            fg_color="transparent",
        ).pack(side="left")

        ctk.CTkFrame(self, fg_color=phil_theme.border_idle, height=1).pack(
            fill="x", padx=14, pady=(8, 12)
        )

        # ── current mode ──────────────────────────────────────────────
        mode_label, provider_label = self._read_current_mode()

        mode_card = ctk.CTkFrame(self, fg_color=phil_theme.surface, corner_radius=8)
        mode_card.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(mode_card, text="AI Mode", text_color=phil_theme.text_dim,
                     font=("Inter", 10), fg_color="transparent").pack(anchor="w", padx=12, pady=(8,0))
        ctk.CTkLabel(mode_card, text=mode_label, text_color=phil_theme.text_main,
                     font=("Inter", 12, "bold"), fg_color="transparent").pack(anchor="w", padx=12)
        ctk.CTkLabel(mode_card, text=provider_label, text_color=phil_theme.text_dim,
                     font=("Inter", 10), fg_color="transparent").pack(anchor="w", padx=12, pady=(0,8))

        ctk.CTkButton(
            self, text="🔄  Switch Mode",
            height=32, corner_radius=8,
            fg_color=phil_theme.btn_voice, hover_color=phil_theme.btn_hover_v,
            text_color="#FFFFFF", font=("Inter", 12, "bold"),
            command=self._on_switch_mode,
        ).pack(fill="x", padx=14, pady=(0, 12))

        # ── memory ───────────────────────────────────────────────────
        mem_card = ctk.CTkFrame(self, fg_color=phil_theme.surface, corner_radius=8)
        mem_card.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(mem_card, text="Build Memory", text_color=phil_theme.text_dim,
                     font=("Inter", 10), fg_color="transparent").pack(anchor="w", padx=12, pady=(8,0))
        count = self._count_memory_entries()
        ctk.CTkLabel(
            mem_card,
            text=f"{count} build{'s' if count != 1 else ''} remembered",
            text_color=phil_theme.text_main,
            font=("Inter", 12, "bold"), fg_color="transparent",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        ctk.CTkButton(
            self, text="🗑  Clear Memory",
            height=32, corner_radius=8,
            fg_color="transparent", border_width=1,
            border_color=phil_theme.danger, text_color=phil_theme.danger,
            font=("Inter", 12),
            command=self._on_clear_memory,
        ).pack(fill="x", padx=14, pady=(0, 12))

        # ── back ──────────────────────────────────────────────────────
        ctk.CTkButton(
            self, text="← Back",
            height=30, corner_radius=8,
            fg_color="transparent", border_width=1,
            border_color=phil_theme.border_idle, text_color=phil_theme.text_dim,
            font=("Inter", 11),
            command=self.show_idle_state,
        ).pack(fill="x", padx=14, pady=(0, 14))

        self._schedule_resize()

    def _read_current_mode(self) -> tuple:
        try:
            import json
            from pathlib import Path
            root = Path(__file__).resolve().parent.parent
            for p in [root / "phil_config.json",
                      root / "voice_input" / "Keys" / "phil_config.json"]:
                if p.exists():
                    data = json.loads(p.read_text())
                    mode = data.get("mode", "unknown")
                    if mode == "local":
                        return "🖥  Local Mode", data.get("local_model", "unknown model")
                    elif mode == "api":
                        return "☁️  API Mode", data.get("provider", "unknown").capitalize()
        except Exception:
            pass
        return "Unknown", "Run setup to configure"

    def _count_memory_entries(self) -> int:
        try:
            import json
            from voice_input.Keys.config import memory_path
            if memory_path.exists():
                data = json.loads(memory_path.read_text())
                return len(data.get("history", []))
        except Exception:
            pass
        return 0

    def _on_clear_memory(self):
        try:
            import json
            from voice_input.Keys.config import memory_path
            with open(memory_path, "w") as f:
                json.dump({}, f)
            print("[Settings] Memory cleared.")
        except Exception as e:
            print(f"[Settings] Clear failed: {e}")
        self._fade_transition(self._build_settings_state)

    def _on_switch_mode(self):
        try:
            self._master._switch_mode()
        except Exception as e:
            print(f"[Settings] Switch mode error: {e}")

    # ══════════════════════════════════════════════════════════════════
    # IDLE RESTORE
    # ══════════════════════════════════════════════════════════════════

    def show_idle_state(self):
        self._fade_transition(self._build_idle_state)

    # ══════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _fade_transition(self, build_fn):
        """Fade window out, rebuild UI, fade back in (~150 ms per phase)."""
        root = self._master
        steps, interval = 6, 25

        def _alpha_supported():
            try:
                root.attributes("-alpha")
                return True
            except Exception:
                return False

        if not _alpha_supported():
            self._clear()
            build_fn()
            return

        def _set_alpha(value):
            root.attributes("-alpha", max(0.0, min(1.0, value)))

        def _fade_out(step=0):
            if step <= steps:
                _set_alpha(1.0 - step / steps)
                self.after(interval, lambda s=step + 1: _fade_out(s))
            else:
                self._clear()
                build_fn()
                _fade_in(0)

        def _fade_in(step=0):
            if step <= steps:
                _set_alpha(step / steps)
                self.after(interval, lambda s=step + 1: _fade_in(s))
            else:
                _set_alpha(1.0)

        _fade_out(0)

    def _clear(self):
        """Destroy all child widgets. Invalidates references like status_label."""
        for w in self.winfo_children():
            w.destroy()

    def _schedule_resize(self):
        """Ask overlay to auto-fit after layout settles (10 ms is enough)."""
        self.after(10, self._master._auto_resize)

    def set_status(self, message: str, state: str = "normal"):
        """
        Update the status label text + border colour.

        CRASH FIX: status_label only exists in idle state.
        In preview/modify/export/script states _clear() has destroyed it.
        We guard with winfo_exists() so the border-colour change still
        works (the frame itself is always alive) without crashing.
        """
        if hasattr(self, "status_label"):
            try:
                # winfo_exists() returns 0 if the widget has been destroyed
                if self.status_label.winfo_exists():
                    self.status_label.configure(text=message.upper())
            except Exception:
                pass  # widget is gone — safe to ignore

        # the frame border always exists, so this is always safe
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