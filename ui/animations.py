"""UI animations for Phil (pulse ring on thinking state)."""

from __future__ import annotations

import math
import tkinter as tk

import customtkinter as ctk


class PulseRing(ctk.CTkFrame):
    """Breathing ring drawn on a tk.Canvas — expands and contracts slowly."""

    def __init__(
        self,
        master,
        color: str = "#FAB387",
        size: int = 44,
        bg_color: str = "#27272A",
        **kwargs,
    ):
        pad = 12
        dim = size + pad * 2
        super().__init__(master, fg_color="transparent", width=dim, height=dim, **kwargs)
        self.pack_propagate(False)
        self._color = color
        self._size = size
        self._bg_color = bg_color
        self._phase = 0.0
        self._running = False
        self._canvas = tk.Canvas(
            self,
            width=dim,
            height=dim,
            highlightthickness=0,
            bd=0,
            bg=bg_color,
        )
        self._canvas.pack(expand=True, fill="both")

    def set_color(self, color: str):
        self._color = color

    def start(self):
        if self._running:
            return
        self._running = True
        self._tick()

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        self._canvas.delete("all")
        dim = self._size + 24
        cx = cy = dim // 2
        base_r = self._size / 2
        r = base_r * (0.82 + 0.18 * math.sin(self._phase))
        self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=self._color,
            width=2,
        )
        self._phase += 0.14
        self.after(45, self._tick)
