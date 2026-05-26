# Phil — Voice & Text to 3D Model

> Describe a 3D part in plain English. Phil generates it in FreeCAD.

Phil is a voice and text-controlled AI assistant that turns natural language descriptions into real 3D CAD models. Built on a deterministic JSON pipeline — your words become geometry, not guesswork.

---

## What it does

You say (or type): **"make a robot servo mount with a hollow rectangular body and two shaft holes"**

Phil:
1. Sends your request to an AI (local or cloud)
2. AI returns a structured JSON spec describing the geometry
3. A deterministic builder converts that spec into a FreeCAD Python script
4. FreeCAD executes the script and exports a `.step` file
5. Phil shows you a 3D preview — accept, modify, or export to Blender

No manual CAD. No clicking. Just describe and build.

---

## System Architecture

```
User (voice / text)
        ↓
   Phil UI (CustomTkinter)
        ↓
  command_bridge.py          ← traffic controller
        ↓
   ai_core.py                ← LLM as planner
   ├── LLMClient              ← unified backend (local or API)
   ├── Asset Library          ← ready-made parts (bolt, flange, gear...)
   ├── Error Memory           ← model learns from past mistakes
   └── JSON spec              ← structured geometry description
        ↓
   builder.py                ← deterministic compiler
   └── FreeCAD Python script  ← no AI hallucination in geometry
        ↓
   runner.py                 ← sandbox executor with self-correction
   └── FreeCAD headless       ← renders .step file
        ↓
   thumbnail.py              ← 3D preview snapshot
        ↓
   Phil UI preview            ← accept / modify / export
```

**Design principles:**
- **LLM = planner.** Understands intent, chooses geometry strategy.
- **Builder = compiler.** Converts JSON to correct FreeCAD code deterministically — no hallucination in the geometry layer.
- **Runner = sandbox.** Catches errors, self-corrects up to 3 times before giving up.
- **Two modes.** Local (Ollama, private, free) or API (Anthropic, OpenAI, Gemini, OpenRouter — better quality).

---

## Prerequisites

| Requirement | Download |
|---|---|
| Python 3.11+ | [python.org](https://python.org) |
| FreeCAD 1.0+ | [freecad.org](https://www.freecad.org) |
| Ollama *(Local mode only)* | [ollama.com](https://ollama.com) |
| API key *(API mode only)* | Anthropic / OpenAI / Gemini / OpenRouter |

---

## Install

```bash
# 1. Clone the repo
git clone https://github.com/Hcone-Eyne/Free_Cad_Extension.git
cd Free_Cad_Extension

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python3 -m voice_input.main
```

First launch opens the **setup screen** — Phil checks your system, lets you choose Local or API mode, and handles the rest automatically.

---

## First Launch

**Local Mode** — runs entirely on your device, no API key needed.
- Requires 8 GB RAM minimum
- Phil recommends the right model for your hardware (3B / 7B / 14B)
- Uses `qwen2.5-coder` via Ollama

**API Mode** — cloud AI, best output quality.
- Supports Anthropic Claude, OpenAI GPT-4o, Google Gemini, OpenRouter
- Enter your API key in the setup screen — stored locally in `.env`

---

## Usage

```
1. Open Phil
2. Click Voice or Text
3. Describe what you want to build
4. Phil generates and shows a 3D preview
5. Accept → export to FreeCAD or Blender
   Modify → describe changes
   View Script → see the generated Python code
```

**Example prompts:**
- `"make a hex bolt M8 40mm long"`
- `"make a flange 50mm outer diameter with 6 bolt holes"`
- `"make a robot servo mount with hollow body and two 8mm shaft holes"`
- `"make a 4x2 Lego brick with hollow bottom"`
- `"make a spur gear 20mm diameter 16 teeth 5mm thick"`

---

## Project Structure

```
Free_Cad_Extension/
├── voice_input/
│   ├── main.py              ← entry point
│   ├── command_bridge.py    ← connects UI to AI + FreeCAD
│   ├── stage_manager.py     ← short-term build memory
│   ├── Keys/
│   │   └── config.py        ← all paths live here
│   └── cad_assist/
│       ├── ai_core.py       ← LLM routing + JSON pipeline
│       ├── builder.py       ← JSON → FreeCAD Python
│       └── runner.py        ← execution + self-correction
├── ui/
│   ├── phil_overlay.py      ← main window + state controller
│   ├── phil_widget.py       ← UI states + animations
│   ├── exporter.py          ← FreeCAD + Blender export
│   └── thumbnail.py         ← 3D preview generator
├── setup/
│   ├── setup_screen.py      ← first launch UI
│   ├── system_check.py      ← RAM, Ollama, FreeCAD detection
│   ├── installer.py         ← Ollama install + model pull
│   └── llm_client.py        ← unified LLM backend
└── speech_processor/
    └── voice_handler.py     ← microphone + speech-to-text
```

---

## Built With

- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — UI framework
- [FreeCAD](https://www.freecad.org) — 3D CAD engine
- [Ollama](https://ollama.com) — local LLM runtime
- [SpeechRecognition](https://github.com/Uberi/speech_recognition) — voice input
- Anthropic / OpenAI / Gemini / OpenRouter — cloud AI providers

---

## License

MIT © 2026 Enoch

---

## Author

Built by **Enoch** — B.E. Computer Science student, building AI systems from scratch.

> Phil is part of a larger vision: invisible, ambient computing where you describe what you need and the machine builds it.
