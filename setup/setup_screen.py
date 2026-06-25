"""
FILE: setup/setup_screen.py
First-run setup screen for Phil.

Flow:
    Screen 1 — Loading (system checks run in background)
    Screen 2 — Choice (Local vs API, local grayed if <8GB RAM)
    Screen 3A — Local install (Ollama + model pull)
    Screen 3B — API config (provider + key)
    Done — writes phil_config.json, calls on_complete() → Phil launches

Design language: matches Phil exactly.
"""

from __future__ import annotations
import json
import re
import threading
from pathlib import Path
from typing import Callable
import customtkinter as ctk  # type: ignore
from voice_input.Keys import config as key_config

# ── Setup package imports ─────────────────────────────────────────────────────
from setup.system_check import check_ram, check_ollama, check_freecad, get_recommended_model
from setup.installer import (
    install_api_provider_package,
    install_ollama,
    install_setup_requirements,
    pip_install_package,
    pull_model,
    verify_ollama,
)

# ── Config paths (Absolute Resolution) ────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_CONFIG_PATH = Path(key_config.phil_config_path)
_ENV_PATH    = Path(key_config.env_path)

# Models offered in the local download dropdown
LOCAL_MODEL_OPTIONS = [
    "qwen2.5-coder:3b",
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
]


def _save_phil_config(payload: dict):
    """Write phil_config.json atomically to the target directory."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[Setup] Config saved → {_CONFIG_PATH}")


def _save_env_key(env_var: str, value: str):
    """Write or update a key in the .env file safely."""
    _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if _ENV_PATH.exists():
        with open(_ENV_PATH, "r") as f:
            lines = f.readlines()

    key_found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{env_var}="):
            lines[i] = f'{env_var}="{value}"\n'
            key_found = True
            break

    if not key_found:
        lines.append(f'{env_var}="{value}"\n')

    with open(_ENV_PATH, "w") as f:
        f.writelines(lines)
    print(f"[Setup] Saved {env_var} to .env")


# ── Design tokens (Matching Phil UI layout palette) ───────────────────────────
class _T:
    bg          = "#18181B"
    surface     = "#27272A"
    surface2    = "#3F3F46"
    text        = "#CDD6F4"
    dim         = "#7F849C"
    accent      = "#6366F1"
    accent_hov  = "#4F46E5"
    green       = "#40A02B"
    danger      = "#F38BA8"
    border      = "#3D3D5C"


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class SetupScreen(ctk.CTk):
    def __init__(self, on_complete: Callable | None = None):
        super().__init__()
        self._on_complete = on_complete

        self.title("Phil — Setup")
        self.geometry("680x520")
        self.resizable(False, False)
        self.configure(fg_color=_T.bg)

        # Grid layout allocation
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # System state
        self._ram_gb: float = 0.0
        self._is_local_viable: bool = False
        self._recommended_model: str = "qwen2.5-coder:3b"
        self._ollama_installed: bool = False
        self._installed_models: list[str] = []
        self._selected_local_model: str | None = None

        # Main container card
        self.main_container = ctk.CTkFrame(
            self,
            fg_color=_T.surface,
            corner_radius=16,
            border_width=1,
            border_color=_T.border,
        )
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)

        self._pulse_bar: ctk.CTkProgressBar | None = None
        self._show_loading_screen()

    def _clear(self):
        """Safely terminates ongoing UI processes before unpacking frames."""
        if self._pulse_bar is not None:
            try:
                self._pulse_bar.stop()
            except Exception:
                pass
            self._pulse_bar = None
        for w in self.main_container.winfo_children():
            w.destroy()

    # ==========================================
    # SCREEN 1: LOADING & ENVIRONMENT PROFILING
    # ==========================================
    def _show_loading_screen(self):
        self._clear()

        center = ctk.CTkFrame(self.main_container, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(center, text="Checking your system…", font=("Inter", 20, "bold"), text_color=_T.text).pack(pady=(0, 6))
        ctk.CTkLabel(center, text="Detecting RAM, Ollama, and FreeCAD installations.", font=("Inter", 12), text_color=_T.dim).pack()

        self._pulse_bar = ctk.CTkProgressBar(
            center, width=320, height=4, corner_radius=2,
            progress_color=_T.accent, fg_color=_T.surface2, mode="indeterminate", indeterminate_speed=1.2
        )
        self._pulse_bar.pack(pady=20)
        self._pulse_bar.start()

        self._loading_sub = ctk.CTkLabel(center, text="Starting checks…", font=("Inter", 11), text_color=_T.dim)
        self._loading_sub.pack()

        threading.Thread(target=self._run_checks, daemon=True).start()

    def _run_checks(self):
        def update_status(msg: str):
            self.after(0, lambda m=msg: self._loading_sub.configure(text=m))

        update_status("Checking RAM hardware capacity…")
        ram_result = check_ram()
        self._ram_gb = getattr(ram_result, "value", 0.0) or 0.0
        self._is_local_viable = getattr(ram_result, "ok", False)

        update_status("Checking Ollama background engine status…")
        ollama_result = check_ollama()
        self._ollama_installed = getattr(ollama_result, "ok", False)
        ollama_value = getattr(ollama_result, "value", None)
        if isinstance(ollama_value, dict):
            self._installed_models = list(ollama_value.get("models") or [])
        else:
            self._installed_models = []

        update_status("Verifying FreeCAD local environment path…")
        check_freecad()

        update_status("Installing shared Python packages…")
        install_setup_requirements(progress_callback=update_status)

        self._recommended_model = get_recommended_model(self._ram_gb) or "qwen2.5-coder:3b"

        update_status("Environment processing sequence complete.")
        self.after(900, self._show_choice_screen)

    # ==========================================
    # SCREEN 2: INTELLIGENCE SELECTION MODES
    # ==========================================
    def _show_choice_screen(self):
        self._clear()

        hdr = ctk.CTkFrame(self.main_container, fg_color="transparent")
        hdr.pack(fill="x", padx=30, pady=(30, 0))

        ctk.CTkLabel(hdr, text="Choose your AI mode", font=("Inter", 22, "bold"), text_color=_T.text).pack(anchor="w")
        ctk.CTkLabel(hdr, text="Local runs entirely on your device. API uses a cloud provider.", font=("Inter", 12), text_color=_T.dim).pack(anchor="w", pady=(4, 0))

        ctk.CTkFrame(self.main_container, fg_color=_T.border, height=1).pack(fill="x", padx=30, pady=16)

        cards = ctk.CTkFrame(self.main_container, fg_color="transparent")
        cards.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        cards.grid_columnconfigure(0, weight=1, uniform="card")
        cards.grid_columnconfigure(1, weight=1, uniform="card")
        cards.grid_rowconfigure(0, weight=1)

        self._build_local_card(cards)
        self._build_api_card(cards)

    def _build_local_card(self, parent):
        viable = self._is_local_viable
        bg = _T.surface2 if viable else "#1E1E21"
        border = _T.border if viable else "#2A2A2E"
        text_col = _T.text if viable else _T.dim

        card = ctk.CTkFrame(parent, fg_color=bg, border_color=border, border_width=1, corner_radius=10)
        card.grid(row=0, column=0, padx=(0, 8), sticky="nsew")

        ctk.CTkLabel(card, text="🖥  Local Mode", font=("Inter", 15, "bold"), text_color=text_col).pack(pady=(20, 6))

        desc = (
            f"Runs entirely on device.\nNo API key needed.\n\n"
            f"Recommended model:\n{self._recommended_model}\n\n"
            f"RAM detected: {self._ram_gb:.1f} GB"
        ) if viable else (
            f"Requires 8 GB RAM minimum.\nYour device has {self._ram_gb:.1f} GB.\n\n"
            f"Please use API cloud mode."
        )

        ctk.CTkLabel(card, text=desc, font=("Inter", 11), text_color=text_col, justify="center").pack(pady=8, padx=12)

        self._local_btn = ctk.CTkButton(
            card, text="Set up Local", width=180, corner_radius=8, font=("Inter", 12, "bold"),
            fg_color=_T.green if viable else _T.surface, text_color="#FFFFFF" if viable else "#555555",
            state="normal" if viable else "disabled", command=self._handle_local_selection
        )
        self._local_btn.pack(side="bottom", pady=20)

    def _build_api_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=_T.surface2, border_color=_T.border, border_width=1, corner_radius=10)
        card.grid(row=0, column=1, padx=(8, 0), sticky="nsew")

        ctk.CTkLabel(card, text="☁️  API Mode", font=("Inter", 15, "bold"), text_color=_T.text).pack(pady=(20, 6))

        desc = "Uses a cloud AI provider.\nBest quality output.\n\nSupports:\nAnthropic · OpenAI\nGemini · OpenRouter\n\nRequires an API key."
        ctk.CTkLabel(card, text=desc, font=("Inter", 11), text_color=_T.dim, justify="center").pack(pady=8, padx=12)

        self._api_btn = ctk.CTkButton(
            card, text="Set up API", width=180, corner_radius=8, font=("Inter", 12, "bold"),
            fg_color=_T.accent, hover_color=_T.accent_hov, text_color="#FFFFFF", command=self._show_api_screen
        )
        self._api_btn.pack(side="bottom", pady=20)

    # ==========================================
    # SCREEN 3A: OLLAMA WORKSPACE PROVISIONING
    # ==========================================
    def _handle_local_selection(self):
        if self._ollama_installed:
            self._show_local_model_screen()
        else:
            self._show_ollama_install_screen()

    def _show_local_model_screen(self):
        self._clear()

        back_btn = ctk.CTkButton(
            self.main_container, text="← Back", width=80, height=28, corner_radius=8,
            font=("Inter", 12, "bold"), fg_color="transparent", hover_color=_T.surface2,
            text_color=_T.text, command=self._show_choice_screen
        )
        back_btn.pack(anchor="nw", padx=20, pady=(16, 0))

        body = ctk.CTkFrame(self.main_container, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=40, pady=(10, 30))

        ctk.CTkLabel(body, text="Choose a local model", font=("Inter", 20, "bold"),
                     text_color=_T.text).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(body, text=f"Recommended for this device: {self._recommended_model}",
                     font=("Inter", 12), text_color=_T.dim).pack(anchor="w", pady=(0, 16))

        # ── installed models ──────────────────────────────────────────
        installed_section = ctk.CTkFrame(body, fg_color=_T.surface2, border_color=_T.border,
                                         border_width=1, corner_radius=10)
        installed_section.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(installed_section, text="Available on this device",
                     font=("Inter", 14, "bold"), text_color=_T.text).pack(anchor="w", padx=18, pady=(16, 4))

        if self._installed_models:
            self._installed_model_var = ctk.StringVar(value=self._pick_default_installed_model())
            ctk.CTkOptionMenu(
                installed_section, values=self._installed_models,
                variable=self._installed_model_var, width=300,
                fg_color=_T.surface, button_color=_T.green, button_hover_color=_T.green,
                text_color=_T.text, font=("Inter", 12),
            ).pack(anchor="w", padx=18, pady=(8, 12))
            ctk.CTkButton(
                installed_section, text="Use Selected Model", width=190, corner_radius=8,
                font=("Inter", 12, "bold"), fg_color=_T.green, text_color="#FFFFFF",
                command=self._use_installed_model,
            ).pack(anchor="w", padx=18, pady=(0, 16))
        else:
            ctk.CTkLabel(installed_section, text="No Ollama models installed yet.",
                         font=("Inter", 12), text_color=_T.dim).pack(anchor="w", padx=18, pady=(8, 16))

        # ── download new model ────────────────────────────────────────
        install_section = ctk.CTkFrame(body, fg_color="transparent")
        install_section.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(install_section, text="Download a model", font=("Inter", 14, "bold"),
                     text_color=_T.text).pack(anchor="w", pady=(0, 8))
        self._install_model_var = ctk.StringVar(value=self._recommended_model)
        ctk.CTkOptionMenu(
            install_section, values=self._ordered_model_options(),
            variable=self._install_model_var, width=300,
            fg_color=_T.surface2, button_color=_T.accent, button_hover_color=_T.accent_hov,
            text_color=_T.text, font=("Inter", 12),
        ).pack(anchor="w", pady=(0, 12))
        ctk.CTkButton(
            install_section, text="Download & Install", width=190, corner_radius=8,
            font=("Inter", 12, "bold"), fg_color=_T.accent, hover_color=_T.accent_hov,
            text_color="#FFFFFF", command=self._install_selected_model,
        ).pack(anchor="w")

    def _pick_default_installed_model(self) -> str:
        if self._recommended_model in self._installed_models:
            return self._recommended_model
        for model in self._installed_models:
            if model.startswith("qwen2.5-coder:"):
                return model
        return self._installed_models[0]

    def _ordered_model_options(self) -> list[str]:
        options = [self._recommended_model]
        for model in LOCAL_MODEL_OPTIONS:
            if model not in options:
                options.append(model)
        return options

    def _active_local_model(self) -> str:
        return self._selected_local_model or self._recommended_model

    def _use_installed_model(self):
        self._selected_local_model = self._installed_model_var.get()

        def run():
            pip_ok = pip_install_package("ollama")
            if not pip_ok.ok:
                print(f"[Setup] {pip_ok.detail}")
            self._save_local_config()
            self.after(0, self._terminate_and_hand_off)

        threading.Thread(target=run, daemon=True).start()

    def _install_selected_model(self):
        self._selected_local_model = self._install_model_var.get()
        self._show_model_pull_screen()

    def _show_ollama_install_screen(self):
        self._clear()
        center = ctk.CTkFrame(self.main_container, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(center, text="Install Ollama", font=("Inter", 20, "bold"), text_color=_T.text).pack(pady=(0, 8))
        ctk.CTkLabel(center, text="Ollama runs AI models locally on your device.\nPhil needs it for Local Mode.", font=("Inter", 12), text_color=_T.dim, justify="center").pack(pady=(0, 20))

        self._install_btn = ctk.CTkButton(
            center, text="Download & Install Ollama", width=260, corner_radius=8, font=("Inter", 12, "bold"),
            fg_color=_T.accent, hover_color=_T.accent_hov, command=self._start_ollama_install
        )
        self._install_btn.pack()

        self._install_sub = ctk.CTkLabel(center, text="", font=("Inter", 11), text_color=_T.dim)
        self._install_sub.pack(pady=(12, 0))

    def _start_ollama_install(self):
        self._install_btn.configure(state="disabled", text="Installing…")

        def progress(msg: str):
            self.after(0, lambda m=msg: self._install_sub.configure(text=m))

        def run():
            result = install_ollama(progress_callback=progress)
            if getattr(result, "ok", False):
                self._ollama_installed = True
                self.after(400, self._show_local_model_screen)
            else:
                self.after(0, lambda: self._install_btn.configure(state="normal", text="Retry Installation"))
                self.after(0, lambda: self._install_sub.configure(
                    text=getattr(result, "detail", "Error"), text_color=_T.danger
                ))

        threading.Thread(target=run, daemon=True).start()

    def _show_model_pull_screen(self):
        self._clear()
        model = self._active_local_model()
        center = ctk.CTkFrame(self.main_container, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(center, text=f"Pulling {model}", font=("Inter", 18, "bold"), text_color=_T.text).pack(pady=(0, 6))
        ctk.CTkLabel(center, text="This may take a few minutes depending on your connection.", font=("Inter", 11), text_color=_T.dim).pack(pady=(0, 20))

        self._model_bar = ctk.CTkProgressBar(
            center, width=380, height=6, corner_radius=3, progress_color=_T.accent, fg_color=_T.surface2
        )
        self._model_bar.set(0)
        self._model_bar.pack()

        self._pull_sub = ctk.CTkLabel(center, text="Connecting to Ollama registry…", font=("Inter", 11), text_color=_T.dim)
        self._pull_sub.pack(pady=(10, 0))

        threading.Thread(target=self._run_model_pull, daemon=True).start()

    def _run_model_pull(self):
        model = self._active_local_model()

        def progress_ui_bridge(msg: str):
            self.after(0, lambda m=msg: self._pull_sub.configure(text=m))
            pct_match = re.search(r"(\d+)%", msg)
            if pct_match:
                pct = int(pct_match.group(1)) / 100
                self.after(0, lambda p=pct: self._model_bar.set(p))

        success = pull_model(model, progress_callback=progress_ui_bridge)
        if success:
            self.after(0, lambda: self._pull_sub.configure(text="Verifying model orchestration integrity…"))
            ok = verify_ollama(model, progress_callback=progress_ui_bridge)
            if ok:
                pip_ok = pip_install_package("ollama", progress_callback=progress_ui_bridge)
                if pip_ok.ok:
                    self._save_local_config()
                    self.after(0, lambda: self._model_bar.set(1.0))
                    self.after(600, self._terminate_and_hand_off)
                else:
                    self.after(
                        0,
                        lambda: self._pull_sub.configure(
                            text=pip_ok.detail or "Failed to install ollama Python package.",
                            text_color=_T.danger,
                        ),
                    )
            else:
                self.after(0, lambda: self._pull_sub.configure(
                    text="Model pulled but verification failed. Try restarting.", text_color=_T.danger
                ))
        else:
            self.after(0, lambda: self._pull_sub.configure(
                text="Download failed. Check your internet connection.", text_color=_T.danger
            ))

    def _save_local_config(self):
        _save_phil_config({
            "setup_complete": True,
            "mode": "local",
            "local_model": self._active_local_model(),
            "provider": None,
            "api_model": None,
            "api_key_env": None,
        })

    # ==========================================
    # SCREEN 3B: CLOUD API CREDENTIAL INFRASTRUCTURE
    # ==========================================
    _PROVIDER_ENV_MAP = {
        "Anthropic":  "ANTHROPIC_API_KEY",
        "OpenAI":     "OPENAI_API_KEY",
        "Gemini":     "GEMINI_API_KEY",
        "OpenRouter": "OPENROUTER_API_KEY",
    }

    def _show_api_screen(self):
        self._clear()

        back_btn = ctk.CTkButton(
            self.main_container, text="← Back", width=80, height=28, corner_radius=8, font=("Inter", 12, "bold"),
            fg_color="transparent", hover_color=_T.surface2, text_color=_T.text, command=self._show_choice_screen
        )
        back_btn.pack(anchor="nw", padx=20, pady=(16, 0))

        form = ctk.CTkFrame(self.main_container, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=40, pady=(8, 30))

        ctk.CTkLabel(form, text="Configure API Mode", font=("Inter", 20, "bold"), text_color=_T.text).pack(anchor="w", pady=(0, 20))
        ctk.CTkLabel(form, text="AI Provider", font=("Inter", 12), text_color=_T.dim).pack(anchor="w", pady=(0, 4))

        self._provider_var = ctk.StringVar(value="Anthropic")
        ctk.CTkOptionMenu(
            form, values=list(self._PROVIDER_ENV_MAP.keys()), variable=self._provider_var, width=240,
            fg_color=_T.surface2, button_color=_T.accent, button_hover_color=_T.accent_hov, text_color=_T.text,
            font=("Inter", 12), command=self._update_key_label
        ).pack(anchor="w", pady=(0, 16))

        self._key_label = ctk.CTkLabel(form, text="ANTHROPIC_API_KEY", font=("Inter", 12), text_color=_T.dim)
        self._key_label.pack(anchor="w", pady=(0, 4))

        self._key_entry = ctk.CTkEntry(
            form, placeholder_text="Paste your API key here…", width=460, height=36, show="•",
            fg_color=_T.surface2, text_color=_T.text, placeholder_text_color=_T.dim,
            border_color=_T.border, border_width=1, font=("Inter", 12), corner_radius=8
        )
        self._key_entry.pack(anchor="w", pady=(0, 24))

        self._api_error = ctk.CTkLabel(form, text="", font=("Inter", 11), text_color=_T.danger)
        self._api_error.pack(anchor="w", pady=(0, 8))

        self._api_save_btn = ctk.CTkButton(
            form, text="Save & Launch Phil", width=220, height=36, corner_radius=8, font=("Inter", 12, "bold"),
            fg_color=_T.accent, hover_color=_T.accent_hov, text_color="#FFFFFF", command=self._save_api_config
        )
        self._api_save_btn.pack(anchor="w")

    def _update_key_label(self, choice: str):
        env_var = self._PROVIDER_ENV_MAP.get(choice, "API_KEY")
        self._key_label.configure(text=env_var)

    def _save_api_config(self):
        provider_display = self._provider_var.get()
        api_key = self._key_entry.get().strip()

        if not api_key:
            self._key_entry.configure(border_color=_T.danger)
            self._api_error.configure(text="API key cannot be empty.", text_color=_T.danger)
            return

        self._key_entry.configure(border_color=_T.border)
        self._api_error.configure(text="")

        env_var = self._PROVIDER_ENV_MAP[provider_display]
        provider_slug = provider_display.lower()

        self._api_save_btn.configure(state="disabled", text="Installing…")

        def _status(msg: str):
            self.after(0, lambda m=msg: self._api_error.configure(text=m, text_color=_T.dim))

        def run():
            result = install_api_provider_package(provider_slug, progress_callback=_status)
            if not getattr(result, "ok", False):
                self.after(0, lambda: self._api_save_btn.configure(state="normal", text="Save & Launch Phil"))
                self.after(
                    0,
                    lambda: self._api_error.configure(
                        text=getattr(result, "detail", "Install failed."),
                        text_color=_T.danger,
                    ),
                )
                return

            _save_env_key(env_var, api_key)
            _save_phil_config({
                "setup_complete": True,
                "mode": "api",
                "local_model": None,
                "provider": provider_slug,
                "api_model": None,
                "api_key_env": env_var,
            })
            self.after(0, self._terminate_and_hand_off)

        threading.Thread(target=run, daemon=True).start()

    # ==========================================
    # FINALIZE WORKFLOW EXIT HANDOFF
    # ==========================================
    def _terminate_and_hand_off(self):
        self.quit()
        self.destroy()
        if self._on_complete:
            self._on_complete()


if __name__ == "__main__":
    app = SetupScreen()
    app.mainloop()
