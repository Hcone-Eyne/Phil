"""
FILE: ui/phil_widget.py

Visual states: idle, thinking, preview, modify, export, script panel.

Design language: Premium, restrained, navy-led palette. Built in Python/Tkinter (tk.Frame + tk.Canvas).
This implementation follows the design spec in Skills/system-design.md exactly.

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
from PIL import Image  # type: ignore

from ui.animations import PulseRing


# ── Design tokens (matching Skills/system-design.md exactly) ────────────────────
class phil_theme:
    # Core palette
    color_bg_canvas       = "#FFFFFF"   # App background / light surfaces
    color_navy_900        = "#14213D"   # Primary surface (header, panels), primary text on light bg
    color_navy_700        = "#1F2E52"   # Hover/active state of navy surfaces
    color_gold_500        = "#C6A15B"   # Accent — status badges, primary CTA, active/selected state
    color_gold_900        = "#412402"   # Text placed on top of gold fills (never black)
    color_grey_400        = "#8A8D93"   # Secondary text, borders, disabled state, dividers
    color_grey_200        = "#D8DAE0"   # Hairline borders on light surfaces
    color_text_on_navy    = "#FFFFFF"   # Primary text/icons on navy surfaces
    color_text_on_navy_muted = "#9AA1B2" # Secondary text on navy surfaces (timestamps, hints)
    color_error           = "#B3261E"   # Error state only — self-correction failures, build errors
    color_success         = "#2E7D32"   # Success state only — successful build/render

    # Legacy aliases for gradual migration (will be removed)
    bg          = color_bg_canvas
    pill_bg     = color_navy_900
    surface     = color_bg_canvas
    surface2    = color_bg_canvas
    border_idle = color_grey_200
    border_focus= color_gold_500
    text_main   = color_navy_900
    text_dim    = color_grey_400
    text_accent = color_gold_500

    btn_voice   = color_navy_900
    btn_text    = color_gold_500
    btn_hover_v = color_navy_700
    btn_hover_t = color_gold_900
    btn_green   = color_success
    btn_hover_g = color_success

    safe        = color_success
    danger      = color_error
    thinking    = color_gold_500

    btn_accept  = color_navy_900
    radius_card = 8
    radius_btn  = 6


class Visual_look_Phill(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=phil_theme.color_bg_canvas,  # White background per design spec
            corner_radius=8,  # 8px for cards/panels
            border_width=0.5,  # 0.5px hairline
            border_color=phil_theme.color_grey_200,
            **kwargs
        )
        self._master = master
        self._current_state = "idle"
        self._pulse_ring: PulseRing | None = None
        self._thinking_label: ctk.CTkLabel | None = None
        self._build_idle_state()

    # ══════════════════════════════════════════════════════════════════
    # IDLE STATE — navy header with gold status badge
    # ═══════════════════════════════════════════════════════════════════

    def _build_idle_state(self):
        self._current_state = "idle"

        # ── Header / status bar (navy surface) ───────────────────────────
        header = ctk.CTkFrame(
            self, 
            fg_color=phil_theme.color_navy_900, 
            corner_radius=0,
            height=44
        )
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        # App name left-aligned
        ctk.CTkLabel(
            header, text="Phil",
            text_color=phil_theme.color_text_on_navy,
            font=("Inter", 15, "normal"),  # 15px medium per spec (regular weight)
            fg_color="transparent",
        ).pack(side="left", padx=(16, 0))

        # ⚙ Settings button — subtle, right-aligned before status badge
        ctk.CTkButton(
            header, text="⚙",
            width=32, height=32, corner_radius=6,
            fg_color="transparent",
            hover_color=phil_theme.color_navy_700,
            text_color=phil_theme.color_text_on_navy_muted,
            font=("Inter", 16),
            command=self._show_settings_state,
        ).pack(side="right", padx=(0, 8))

        # Status badge right-aligned: gold bg, gold-900 text, 6px radius
        self.status_badge = ctk.CTkLabel(
            header, text="Ready",
            text_color=phil_theme.color_gold_900,
            font=("Inter", 12, "normal"),
            fg_color=phil_theme.color_gold_500,
            corner_radius=6,
            padx=12,
            pady=4,
        )
        self.status_badge.pack(side="right", padx=(0, 16))

        # ── Divider (hairline) ───────────────────────────────────────────
        div = ctk.CTkFrame(self, fg_color=phil_theme.color_grey_200, height=0.5)
        div.pack(fill="x", padx=16, pady=(8, 12))

        # ── Action buttons ───────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=16, pady=(0, 16))

        # Primary button: navy bg, white text — reserve for one primary action
        self.voice_btn = ctk.CTkButton(
            btn_row, text="Voice",
            width=120, height=36, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.color_navy_900,
            hover_color=phil_theme.color_navy_700,
            text_color=phil_theme.color_text_on_navy,
            font=("Inter", 13, "normal"),  # Sentence case, no bold
            command=self.master.on_voice_click,
        )
        self.voice_btn.pack(side="left", padx=(0, 8))

        # Secondary button: transparent bg, grey-200 border, navy text
        self.text_btn = ctk.CTkButton(
            btn_row, text="Text",
            width=120, height=36, corner_radius=phil_theme.radius_btn,
            fg_color="transparent",
            border_width=0.5,
            border_color=phil_theme.color_grey_200,
            text_color=phil_theme.color_navy_900,
            hover_color=phil_theme.color_bg_canvas,
            font=("Inter", 13, "normal"),
            command=self.master.on_text_click,
        )
        self.text_btn.pack(side="left")

        # ── Text entry (hidden until Text is clicked) ────────────────────
        self.entry_frame = ctk.CTkFrame(self, fg_color="transparent")

        self.entry = ctk.CTkEntry(
            self.entry_frame,
            placeholder_text="Type your command…",
            width=235, height=36,
            fg_color=phil_theme.color_bg_canvas,
            text_color=phil_theme.color_navy_900,
            placeholder_text_color=phil_theme.color_grey_400,
            border_color=phil_theme.color_grey_200,
            border_width=0.5,
            font=("Inter", 13),
            corner_radius=phil_theme.radius_btn,
        )
        self.entry.pack(side="left", padx=(0, 6))
        self.entry.bind("<Return>", lambda e: self.master.on_text_submit(self.entry.get()))

        ctk.CTkButton(
            self.entry_frame, text="→",
            width=36, height=36, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.color_navy_900,
            hover_color=phil_theme.color_navy_700,
            text_color=phil_theme.color_text_on_navy,
            font=("Inter", 16, "normal"),
            command=lambda: self.master.on_text_submit(self.entry.get()),
        ).pack(side="left")

        self._schedule_resize()

    # ══════════════════════════════════════════════════════════════════
    # THINKING STATE — shown while AI is processing
    # ═══════════════════════════════════════════════════════════════════

    def show_thinking_state(self, message: str = "Thinking…"):
        self._clear()
        self._current_state = "thinking"
        
        # Header area for context
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            header, text="Building",
            text_color=phil_theme.color_gold_500,
            font=("Inter", 14, "normal"),
            fg_color="transparent",
        ).pack(side="left")

        # PulseRing: gold for active/processing, grey for idle, error for failure
        self._pulse_ring = PulseRing(
            self, color=phil_theme.color_gold_500, bg_color=phil_theme.color_bg_canvas,
        )
        self._pulse_ring.pack(pady=(12, 4))
        self._pulse_ring.start()

        self._thinking_label = ctk.CTkLabel(
            self, text=message,
            text_color=phil_theme.color_gold_500,
            font=("Inter", 13, "normal"),
            fg_color="transparent",
        )
        self._thinking_label.pack(pady=(2, 8), padx=16)

        # Self-correction loading bar (flat, no glow)
        # Track: color_grey_200, Fill: color_gold_500 while retrying
        self._thinking_progress = ctk.CTkProgressBar(
            self,
            width=320,
            height=6,
            corner_radius=3,
            fg_color=phil_theme.color_grey_200,
            progress_color=phil_theme.color_gold_500,
        )
        self._thinking_progress.pack(pady=(4, 16), padx=16)
        self._thinking_progress.configure(mode="indeterminate")
        self._thinking_progress.start()

        self._schedule_resize()

    def update_thinking_label(self, message: str):
        if self._thinking_label is not None:
            try:
                if self._thinking_label.winfo_exists():
                    self._thinking_label.configure(text=message)
            except Exception:
                pass
        msg = message.lower()
        if any(k in msg for k in ("fix", "done", "✓", "success")):
            color, border = phil_theme.color_success, phil_theme.color_success
        elif any(k in msg for k in ("fail", "error", "could not")):
            color, border = phil_theme.color_error, phil_theme.color_error
        else:
            color, border = phil_theme.color_gold_500, phil_theme.color_gold_500
        if self._thinking_label is not None:
            try:
                if self._thinking_label.winfo_exists():
                    self._thinking_label.configure(text_color=color)
            except Exception:
                pass
        if self._pulse_ring is not None:
            try:
                self._pulse_ring.set_color(color)
            except Exception:
                pass
        if hasattr(self, "_thinking_progress") and self._thinking_progress is not None:
            try:
                if self._thinking_progress.winfo_exists():
                    self._thinking_progress.configure(progress_color=color)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════
    # PREVIEW STATE — thumbnail + prompt + accept/modify
    # ══════════════════════════════════════════════════════════════════

    def show_preview_state(self, thumb_path, prompt_text, on_accept, on_modify, on_script):
        self._clear()
        self._current_state = "preview"

        # ── Header bar ────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            hdr, text="3D Preview",
            text_color=phil_theme.color_gold_500,
            font=("Inter", 14, "normal"),
            fg_color="transparent",
        ).pack(side="left")
        ctk.CTkLabel(
            hdr, text="Click image to view script",
            text_color=phil_theme.color_text_on_navy_muted,
            font=("Inter", 12, "normal"),
            fg_color="transparent",
        ).pack(side="right")

        # ── Thumbnail ─────────────────────────────────────────────────
        # White bg, 0.5px color_grey_200 border, 8px radius, no accent unless active build
        thumb_frame = ctk.CTkFrame(
            self, 
            fg_color=phil_theme.color_bg_canvas, 
            corner_radius=phil_theme.radius_card,
            border_width=0.5,
            border_color=phil_theme.color_grey_200,
        )
        thumb_frame.pack(pady=(8, 0), padx=16, fill="x")

        if thumb_path and thumb_path.exists():
            img = Image.open(thumb_path)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(340, 190))
            thumb_label = ctk.CTkLabel(thumb_frame, image=ctk_img, text="")
        else:
            thumb_label = ctk.CTkLabel(
                thumb_frame,
                text="3D Preview Unavailable",
                text_color=phil_theme.color_grey_400,
                font=("Inter", 13, "normal"),
                fg_color="transparent",
                height=196,
            )

        thumb_label.pack(padx=8, pady=8)

        # Script hint overlay on hover
        script_hint = ctk.CTkLabel(
            thumb_frame, text="View Script",
            text_color=phil_theme.color_text_on_navy,
            fg_color=phil_theme.color_navy_900,
            font=("Inter", 10, "normal"),
            corner_radius=6,
            padx=10,
            pady=4,
        )
        thumb_label.bind("<Enter>", lambda e: script_hint.place(relx=0.5, rely=0.9, anchor="center"))
        thumb_label.bind("<Leave>", lambda e: script_hint.place_forget())
        thumb_label.bind("<Button-1>", lambda e: on_script())
        thumb_label.configure(cursor="hand2")

        # ── Prompt chip ───────────────────────────────────────────────
        prompt_chip = ctk.CTkFrame(
            self, 
            fg_color=phil_theme.color_bg_canvas, 
            corner_radius=phil_theme.radius_btn,
            border_width=0.5,
            border_color=phil_theme.color_grey_200,
        )
        prompt_chip.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            prompt_chip,
            text=f'"{prompt_text}"',
            text_color=phil_theme.color_grey_400,
            font=("Inter", 12, "italic"),
            wraplength=340,
            justify="left",
            fg_color="transparent",
        ).pack(padx=12, pady=8, anchor="w")

        # ── Action buttons ────────────────────────────────────────────
        # Primary: navy bg, white text — reserve for one primary action (Accept)
        # Secondary: transparent bg, grey-200 border, navy text
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(12, 16), padx=16)

        ctk.CTkButton(
            btn_row, text="Accept",
            width=160, height=38, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.color_navy_900,
            hover_color=phil_theme.color_navy_700,
            text_color=phil_theme.color_text_on_navy,
            font=("Inter", 13, "normal"),
            command=on_accept,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Modify",
            width=160, height=38, corner_radius=phil_theme.radius_btn,
            fg_color="transparent",
            border_width=0.5,
            border_color=phil_theme.color_grey_200,
            text_color=phil_theme.color_navy_900,
            hover_color=phil_theme.color_bg_canvas,
            font=("Inter", 13, "normal"),
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
        div = ctk.CTkFrame(self, fg_color=phil_theme.color_grey_200, height=0.5)
        div.pack(fill="x", padx=16, pady=(8, 8))

        ctk.CTkLabel(
            self, text="Describe your modification",
            text_color=phil_theme.color_grey_400,
            font=("Inter", 12, "normal"),
            fg_color="transparent",
        ).pack(anchor="w", padx=16)

        self.modify_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.modify_frame.pack(pady=(4, 16), padx=16, fill="x")

        self.modify_entry = ctk.CTkEntry(
            self.modify_frame,
            placeholder_text="e.g. make it taller by 10mm…",
            height=38,
            fg_color=phil_theme.color_bg_canvas,
            text_color=phil_theme.color_navy_900,
            placeholder_text_color=phil_theme.color_grey_400,
            border_color=phil_theme.color_grey_200,
            border_width=0.5,
            font=("Inter", 13, "normal"),
            corner_radius=phil_theme.radius_btn,
        )
        self.modify_entry.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.modify_entry.bind("<Return>", lambda e: on_submit(self.modify_entry.get()))
        self.modify_entry.focus()

        # Primary action: navy bg, white text
        ctk.CTkButton(
            self.modify_frame, text="→",
            width=38, height=38, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.color_navy_900,
            hover_color=phil_theme.color_navy_700,
            text_color=phil_theme.color_text_on_navy,
            font=("Inter", 16, "normal"),
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
        self._export_buttons = []

        # ── header ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(16, 0))
        ctk.CTkLabel(
            hdr, text="Export Model",
            text_color=phil_theme.color_navy_900,
            font=("Inter", 16, "normal"),
            fg_color="transparent",
        ).pack(side="left")

        # ── divider ──────────────────────────────────────────────────
        ctk.CTkFrame(self, fg_color=phil_theme.color_grey_200, height=0.5).pack(
            fill="x", padx=16, pady=(8, 12)
        )

        ctk.CTkLabel(
            self, text="Choose format and action",
            text_color=phil_theme.color_grey_400,
            font=("Inter", 13, "normal"),
            fg_color="transparent",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        # ── card builder ──────────────────────────────────────────────
        def _card(icon, name, fmt, save_cb, open_cb, reveal_cb):
            card = ctk.CTkFrame(
                self, 
                fg_color=phil_theme.color_bg_canvas, 
                corner_radius=phil_theme.radius_card,
                border_width=0.5,
                border_color=phil_theme.color_grey_200,
            )
            card.pack(padx=16, pady=(0, 8), fill="x")

            # title row
            title_row = ctk.CTkFrame(card, fg_color="transparent")
            title_row.pack(fill="x", padx=12, pady=(10, 4))

            ctk.CTkLabel(
                title_row, text=icon,
                font=("Inter", 16),
                fg_color="transparent",
                text_color=phil_theme.color_navy_900,
            ).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(
                title_row, text=name,
                font=("Inter", 13, "normal"),
                text_color=phil_theme.color_navy_900,
                fg_color="transparent",
            ).pack(side="left")

            ctk.CTkLabel(
                title_row, text=fmt,
                font=("Inter", 12, "normal"),
                text_color=phil_theme.color_grey_400,
                fg_color="transparent",
            ).pack(side="left", padx=(6, 0))

            # button row
            btn_row = ctk.CTkFrame(card, fg_color="transparent")
            btn_row.pack(fill="x", padx=12, pady=(0, 10))

            btn_save = ctk.CTkButton(
                btn_row, text="Save to…",
                height=34, corner_radius=phil_theme.radius_btn,
                fg_color=phil_theme.color_navy_900,
                hover_color=phil_theme.color_navy_700,
                text_color=phil_theme.color_text_on_navy,
                font=("Inter", 12, "normal"),
                command=save_cb,
            )
            btn_save.pack(side="left", padx=(0, 5))
            self._export_buttons.append(btn_save)

            btn_open = ctk.CTkButton(
                btn_row, text="Open in App",
                height=34, corner_radius=phil_theme.radius_btn,
                fg_color=phil_theme.color_navy_900,
                hover_color=phil_theme.color_navy_700,
                text_color=phil_theme.color_text_on_navy,
                font=("Inter", 12, "normal"),
                command=open_cb,
            )
            btn_open.pack(side="left", padx=(0, 5))
            self._export_buttons.append(btn_open)

            btn_reveal = ctk.CTkButton(
                btn_row, text="Reveal",
                height=34, corner_radius=phil_theme.radius_btn,
                fg_color="transparent",
                border_width=0.5,
                border_color=phil_theme.color_grey_200,
                text_color=phil_theme.color_grey_400,
                hover_color=phil_theme.color_bg_canvas,
                font=("Inter", 12, "normal"),
                command=reveal_cb,
            )
            btn_reveal.pack(side="left")
            self._export_buttons.append(btn_reveal)

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

        self.back_btn = ctk.CTkButton(
            self, text="← Back to Idle",
            height=36, corner_radius=phil_theme.radius_btn,
            fg_color="transparent",
            border_width=0.5,
            border_color=phil_theme.color_grey_200,
            text_color=phil_theme.color_grey_400,
            hover_color=phil_theme.color_bg_canvas,
            font=("Inter", 12, "normal"),
            command=on_back,
        )
        self.back_btn.pack(pady=(0, 16), padx=16, fill="x")
        self._export_buttons.append(self.back_btn)

        self._schedule_resize()

    def show_export_loading(self, show: bool, message: str = ""):
        """
        Shows/hides the export loading bar and status label.
        Disables/enables export buttons to prevent double actions.
        """
        # 1. Update button states
        state = "disabled" if show else "normal"
        if hasattr(self, "_export_buttons"):
            for btn in self._export_buttons:
                try:
                    if btn.winfo_exists():
                        btn.configure(state=state)
                except Exception:
                    pass

        # 2. Handle progress bar & status label
        if show:
            if not hasattr(self, "_export_loading_frame") or self._export_loading_frame is None or not self._export_loading_frame.winfo_exists():
                self._export_loading_frame = ctk.CTkFrame(self, fg_color="transparent")
                
                # Temporarily unpack back_btn so loading bar goes above it
                if hasattr(self, "back_btn") and self.back_btn.winfo_exists():
                    self.back_btn.pack_forget()

                self._export_loading_frame.pack(pady=(4, 10), padx=16, fill="x")

                self._export_status_lbl = ctk.CTkLabel(
                    self._export_loading_frame,
                    text=message,
                    text_color=phil_theme.color_gold_500,
                    font=("Inter", 12, "normal"),
                    fg_color="transparent",
                )
                self._export_status_lbl.pack(anchor="w", padx=2, pady=(0, 4))

                self._export_progress = ctk.CTkProgressBar(
                    self._export_loading_frame,
                    height=6,
                    corner_radius=3,
                    fg_color=phil_theme.color_grey_200,
                    progress_color=phil_theme.color_gold_500,
                )
                self._export_progress.pack(fill="x")
                self._export_progress.configure(mode="indeterminate")
                self._export_progress.start()

                # Repack back_btn
                if hasattr(self, "back_btn") and self.back_btn.winfo_exists():
                    self.back_btn.pack(pady=(0, 16), padx=16, fill="x")
            else:
                if hasattr(self, "_export_status_lbl") and self._export_status_lbl.winfo_exists():
                    self._export_status_lbl.configure(text=message)
        else:
            if hasattr(self, "_export_loading_frame") and self._export_loading_frame is not None:
                try:
                    if self._export_loading_frame.winfo_exists():
                        self._export_loading_frame.destroy()
                except Exception:
                    pass
            self._export_loading_frame = None

        self._schedule_resize()

    # ══════════════════════════════════════════════════════════════════
    # SCRIPT PANEL
    # ══════════════════════════════════════════════════════════════════

    def show_script_panel(self, code: str, on_back=None):
        self._clear()
        self._current_state = "script"
        self._script_back = on_back

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(16, 0))
        ctk.CTkLabel(
            hdr, text="Generated Script",
            text_color=phil_theme.color_gold_500,
            font=("Inter", 14, "normal"),
            fg_color="transparent",
        ).pack(side="left")

        ctk.CTkFrame(self, fg_color=phil_theme.color_grey_200, height=0.5).pack(
            fill="x", padx=16, pady=(8, 6)
        )

        code_box = ctk.CTkTextbox(
            self,
            height=300,
            fg_color=phil_theme.color_navy_900,
            text_color=phil_theme.color_text_on_navy,
            font=("JetBrains Mono", 11),
            corner_radius=8,
            border_width=0.5,
            border_color=phil_theme.color_grey_200,
        )
        code_box.pack(padx=16, pady=(0, 8), fill="both")
        code_box.insert("0.0", code)
        code_box.configure(state="disabled")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(0, 16), padx=16, fill="x")

        def _copy():
            self.clipboard_clear()
            self.clipboard_append(code)

        ctk.CTkButton(
            btn_row, text="Copy",
            height=34, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.color_navy_900,
            hover_color=phil_theme.color_navy_700,
            text_color=phil_theme.color_text_on_navy,
            font=("Inter", 12, "normal"),
            command=_copy,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="← Back",
            height=34, corner_radius=phil_theme.radius_btn,
            fg_color="transparent",
            border_width=0.5,
            border_color=phil_theme.color_grey_200,
            text_color=phil_theme.color_grey_400,
            hover_color=phil_theme.color_bg_canvas,
            font=("Inter", 12, "normal"),
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
        hdr.pack(fill="x", padx=16, pady=(16, 0))
        ctk.CTkLabel(
            hdr, text="Settings",
            text_color=phil_theme.color_navy_900,
            font=("Inter", 16, "normal"),
            fg_color="transparent",
        ).pack(side="left")

        ctk.CTkFrame(self, fg_color=phil_theme.color_grey_200, height=0.5).pack(
            fill="x", padx=16, pady=(8, 12)
        )

        # ── current mode ──────────────────────────────────────────────
        mode_label, provider_label = self._read_current_mode()

        mode_card = ctk.CTkFrame(
            self, 
            fg_color=phil_theme.color_bg_canvas,
            corner_radius=phil_theme.radius_card,
            border_width=0.5,
            border_color=phil_theme.color_grey_200,
        )
        mode_card.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(mode_card, text="AI Mode", text_color=phil_theme.color_grey_400,
                     font=("Inter", 12, "normal"), fg_color="transparent").pack(anchor="w", padx=12, pady=(8,0))
        ctk.CTkLabel(mode_card, text=mode_label, text_color=phil_theme.color_navy_900,
                     font=("Inter", 13, "normal"), fg_color="transparent").pack(anchor="w", padx=12)
        ctk.CTkLabel(mode_card, text=provider_label, text_color=phil_theme.color_grey_400,
                     font=("Inter", 12, "normal"), fg_color="transparent").pack(anchor="w", padx=12, pady=(0,8))

        ctk.CTkButton(
            self, text="Switch Mode",
            height=34, corner_radius=phil_theme.radius_btn,
            fg_color=phil_theme.color_navy_900, hover_color=phil_theme.color_navy_700,
            text_color=phil_theme.color_text_on_navy, font=("Inter", 13, "normal"),
            command=self._on_switch_mode,
        ).pack(fill="x", padx=16, pady=(0, 12))

        # ── memory ───────────────────────────────────────────────────
        mem_card = ctk.CTkFrame(
            self, 
            fg_color=phil_theme.color_bg_canvas,
            corner_radius=phil_theme.radius_card,
            border_width=0.5,
            border_color=phil_theme.color_grey_200,
        )
        mem_card.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(mem_card, text="Build Memory", text_color=phil_theme.color_grey_400,
                     font=("Inter", 12, "normal"), fg_color="transparent").pack(anchor="w", padx=12, pady=(8,0))
        count = self._count_memory_entries()
        ctk.CTkLabel(
            mem_card,
            text=f"{count} build{'s' if count != 1 else ''} remembered",
            text_color=phil_theme.color_navy_900,
            font=("Inter", 13, "normal"), fg_color="transparent",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        ctk.CTkButton(
            self, text="Clear Memory",
            height=34, corner_radius=phil_theme.radius_btn,
            fg_color="transparent", border_width=0.5,
            border_color=phil_theme.color_error, text_color=phil_theme.color_error,
            hover_color=phil_theme.color_bg_canvas,
            font=("Inter", 12, "normal"),
            command=self._on_clear_memory,
        ).pack(fill="x", padx=16, pady=(0, 12))

        # ── back ──────────────────────────────────────────────────────
        ctk.CTkButton(
            self, text="← Back",
            height=34, corner_radius=phil_theme.radius_btn,
            fg_color="transparent", border_width=0.5,
            border_color=phil_theme.color_grey_200, text_color=phil_theme.color_grey_400,
            hover_color=phil_theme.color_bg_canvas,
            font=("Inter", 12, "normal"),
            command=self.show_idle_state,
        ).pack(fill="x", padx=16, pady=(0, 16))

        self._schedule_resize()

    def _read_current_mode(self) -> tuple:
        try:
            import json
            from voice_input.Keys.config import phil_config_path
            p = phil_config_path
            if p.exists():
                data = json.loads(p.read_text())
                mode = data.get("mode", "unknown")
                if mode == "local":
                    return "Local Mode", data.get("local_model", "unknown model")
                elif mode == "api":
                    return "API Mode", data.get("provider", "unknown").capitalize()
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
        if self._pulse_ring is not None:
            try:
                self._pulse_ring.stop()
            except Exception:
                pass
        self._pulse_ring = None
        self._thinking_label = None
        for w in self.winfo_children():
            w.destroy()

    def _schedule_resize(self):
        """Ask overlay to auto-fit after layout settles (10 ms is enough)."""
        self.after(10, self._master._auto_resize)

    def set_status(self, message: str, state: str = "normal"):
        """
        Update the status badge text + color.

        CRASH FIX: status_badge only exists in idle state.
        In preview/modify/export/script states _clear() has destroyed it.
        We guard with winfo_exists() so the border-colour change still
        works (the frame itself is always alive) without crashing.
        """
        if hasattr(self, "status_badge"):
            try:
                if self.status_badge.winfo_exists():
                    self.status_badge.configure(text=message)
            except Exception:
                pass  # widget is gone — safe to ignore

        # Update badge color based on state
        colors = {
            "safe":     (phil_theme.color_success, phil_theme.color_gold_900),
            "danger":   (phil_theme.color_error, "#FFFFFF"),
            "thinking": (phil_theme.color_gold_500, phil_theme.color_gold_900),
            "normal":   (phil_theme.color_gold_500, phil_theme.color_gold_900),
        }
        bg, fg = colors.get(state, (phil_theme.color_gold_500, phil_theme.color_gold_900))
        if hasattr(self, "status_badge"):
            try:
                if self.status_badge.winfo_exists():
                    self.status_badge.configure(fg_color=bg, text_color=fg)
            except Exception:
                pass

    def show_text_entry(self):
        self.entry_frame.pack(padx=16, pady=(0, 16))
        self.entry.delete(0, "end")
        self.entry.focus()
        self._schedule_resize()

    def hide_text_entry(self):
        self.entry_frame.pack_forget()
        self._schedule_resize()

    def set_voice_active(self, active: bool):
        if hasattr(self, "voice_btn") and self.voice_btn.winfo_exists():
            self.voice_btn.configure(
                fg_color=phil_theme.color_error if active else phil_theme.color_navy_900,
                text="Stop" if active else "Voice",
            )