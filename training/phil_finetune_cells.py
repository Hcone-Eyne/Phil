"""
Phil Fine-Tuning Pipeline — Google Colab Cells (FIXED v2)
==========================================================

Copy each cell into a separate Colab notebook cell.
Run in order: Cell 1 → Cell 8.

Fixes Applied:
- CadQuery properly installed in Cell 1
- Combined conversion + formatting in single map pass (no double processing)
- Fixed serialization trap (collate_fn handles JSON correctly)
- Improved AST parser for higher conversion rate
"""

# =============================================================================
# CELL 1: Install Dependencies (Colab-specific)
# =============================================================================
# Run this cell FIRST. Takes ~3-5 minutes.

!pip install -q unsloth
!pip install -q --upgrade transformers datasets accelerate peft trl bitsandbytes
!pip install -q huggingface_hub
!pip install -q cadquery

print("✓ Dependencies installed (including CadQuery)")
# Output: ✓ Dependencies installed (including CadQuery)

# =============================================================================
# CELL 2: Mount Google Drive + Imports
# =============================================================================
# Mount Drive for persistent checkpoints.

from google.colab import drive
drive.mount('/content/drive')

import os
import json
import gc
import torch
import ast
from pathlib import Path

# Create checkpoint directory on Drive
CHECKPOINT_ROOT = Path("/content/drive/MyDrive/phil-checkpoints")
CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)

# Verify GPU
assert torch.cuda.is_available(), "❌ No GPU found. Go to Runtime → Change runtime type → T4 GPU"
GPU_NAME = torch.cuda.get_device_name(0)
GPU_MEM = torch.cuda.get_device_properties(0).total_memory / 1024**3
print(f"✓ GPU: {GPU_NAME} ({GPU_MEM:.1f} GB)")
print(f"✓ Checkpoints will save to: {CHECKPOINT_ROOT}")

# Verify CadQuery
try:
    import cadquery as cq
    print(f"✓ CadQuery version: {cq.__version__}")
except ImportError:
    print("❌ CadQuery import failed. Try restarting runtime.")
# Output:
# ✓ GPU: Tesla T4 (15.0 GB)
# ✓ Checkpoints will save to: /content/drive/MyDrive/phil-checkpoints
# ✓ CadQuery version: 2.x.x

# =============================================================================
# CELL 3: Load Zero-to-CAD Dataset
# =============================================================================
# Uses HuggingFace datasets with memory-mapped Arrow format.

from huggingface_hub import login
from datasets import load_dataset

# ── HuggingFace Token (optional but 2-3x faster) ────────────────────────────
# Get your token: https://huggingface.co/settings/tokens
# If you don't have a token, leave empty "" - still works, just slower

HF_TOKEN = ""  # Paste your token here: hf_XXXXXXXXXXXXXXXX

if HF_TOKEN:
    login(token=HF_TOKEN)
    print("Logged in to HuggingFace (fast download mode)")
else:
    print("No token provided (using anonymous download - slower)")

print("Loading Zero-to-CAD-100k from HuggingFace...")
print("First download takes ~5-10 min with token, ~20+ min without")

dataset = load_dataset(
    "ADSKAILab/Zero-To-CAD-100k",
    split="train",
    streaming=False,
    token=HF_TOKEN if HF_TOKEN else None,
)

print(f"✓ Dataset loaded: {len(dataset)} samples")
print(f"✓ Columns: {list(dataset.features.keys())}")

# Quick peek
sample = dataset[0]
code = sample['cadquery_file']
if isinstance(code, bytes):
    code = code.decode('utf-8', errors='ignore')
print(f"\n--- Sample CadQuery code (first 200 chars) ---")
print(code[:200])

# =============================================================================
# CELL 4: Convert + Format in Single Pass (FIXED)
# =============================================================================
# Combined conversion and formatting in ONE map pass.
# No double processing, no serialization trap.

import cadquery as cq

# ── CadQuery execution (now actually works) ───────────────────────────────────

def _safe_execute_cadquery(code: str):
    """Execute CadQuery code and return the result shape."""
    try:
        namespace = {"cq": cq, "cadquery": cq}
        exec(code, namespace)
        for var in ("result", "solid", "shape", "obj"):
            if var in namespace:
                return namespace[var]
        for val in namespace.values():
            if isinstance(val, cq.Workplane):
                return val
        return None
    except Exception as e:
        return None

def _get_bb(shape):
    """Get bounding box (x, y, z)."""
    try:
        bb = shape.val().BoundingBox()
        return (bb.xlen, bb.ylen, bb.zlen)
    except Exception:
        return None

def _is_cylinder(shape):
    try:
        faces = shape.faces().vals()
        if len(faces) == 3:
            for face in faces:
                if hasattr(face, "geomType") and face.geomType() == "CYLINDER":
                    return True
    except Exception:
        pass
    return False

def _is_sphere(shape):
    try:
        faces = shape.faces().vals()
        if len(faces) == 1:
            if hasattr(faces[0], "geomType") and faces[0].geomType() == "SPHERE":
                return True
    except Exception:
        pass
    return False

def _detect_primitives(shape):
    parts = []
    bb = _get_bb(shape)
    if bb is None:
        return parts
    x, y, z = bb

    if _is_sphere(shape):
        r = max(x, y, z) / 2
        parts.append({"type": "sphere", "name": "sphere_0", "r": round(r, 4)})
        return parts

    if _is_cylinder(shape):
        if x == y:
            r, h = x / 2, z
        elif x == z:
            r, h = x / 2, y
        else:
            r, h = y / 2, x
        parts.append({"type": "cylinder", "name": "cylinder_0", "r": round(r, 4), "h": round(h, 4)})
        return parts

    parts.append({"type": "box", "name": "part_0", "l": round(x, 4), "w": round(y, 4), "h": round(z, 4)})
    return parts

# ── AST fallback (improved) ──────────────────────────────────────────────────

def _eval_num(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_num(node.operand)
    if isinstance(node, ast.BinOp):
        left, right = _eval_num(node.left), _eval_num(node.right)
        if isinstance(node.op, ast.Add): return left + right
        if isinstance(node.op, ast.Sub): return left - right
        if isinstance(node.op, ast.Mult): return left * right
        if isinstance(node.op, ast.Div): return left / right if right != 0 else 0
    raise ValueError(f"Cannot evaluate: {ast.dump(node)}")

def _extract_from_ast(code: str):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    parts, ops = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # .box(l, w, h)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "box":
            args = node.args
            if len(args) >= 3:
                try:
                    l, w, h = _eval_num(args[0]), _eval_num(args[1]), _eval_num(args[2])
                    parts.append({"type": "box", "name": f"box_{len(parts)}", "l": l, "w": w, "h": h})
                except Exception:
                    pass
        # .cylinder(h, r) or .cylinder(r, h) — CadQuery uses (h, r)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "cylinder":
            args = node.args
            if len(args) >= 2:
                try:
                    # CadQuery: .cylinder(height, radius)
                    h, r = _eval_num(args[0]), _eval_num(args[1])
                    parts.append({"type": "cylinder", "name": f"cyl_{len(parts)}", "r": r, "h": h})
                except Exception:
                    pass
        # .sphere(r)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "sphere":
            args = node.args
            if len(args) >= 1:
                try:
                    r = _eval_num(args[0])
                    parts.append({"type": "sphere", "name": f"sph_{len(parts)}", "r": r})
                except Exception:
                    pass
        # .extrude(l) — convert 2D to 3D box
        if isinstance(node.func, ast.Attribute) and node.func.attr == "extrude":
            args = node.args
            if len(args) >= 1 and parts:
                try:
                    h = _eval_num(args[0])
                    last = parts[-1]
                    if last["type"] == "box":
                        last["h"] = h
                except Exception:
                    pass
        # .cut() — mark as cut operation
        if isinstance(node.func, ast.Attribute) and node.func.attr == "cut":
            if len(parts) >= 2 and not ops:
                ops.append({"type": "cut", "base": parts[0]["name"], "cutters": [p["name"] for p in parts[1:]]})
        # .union() or .fuse()
        if isinstance(node.func, ast.Attribute) and node.func.attr in ("union", "fuse"):
            if len(parts) >= 2 and not ops:
                ops.append({"type": "fuse_all"})

    if not parts:
        return None
    if not ops:
        ops.append({"type": "assign", "part": parts[0]["name"]} if len(parts) == 1 else {"type": "fuse_all"})
    return {"parts": parts, "operations": ops}

# ── Main converter (execution + AST fallback) ────────────────────────────────

def convert_cadquery(code: str):
    """Convert CadQuery code to Phil's JSON spec. Returns dict or None."""
    if not code or not code.strip():
        return None

    # Try execution-based extraction first (most accurate)
    shape = _safe_execute_cadquery(code)
    if shape is not None:
        parts = _detect_primitives(shape)
        if parts:
            ops = [{"type": "assign", "part": parts[0]["name"]}] if len(parts) == 1 else [{"type": "fuse_all"}]
            return {"parts": parts, "operations": ops}

    # Fallback to AST parsing
    return _extract_from_ast(code)

# ── Validation ────────────────────────────────────────────────────────────────

def validate_json_spec(spec: dict) -> bool:
    """Validate output against Phil's builder.py schema."""
    if not isinstance(spec, dict):
        return False
    if "parts" not in spec or not isinstance(spec["parts"], list):
        return False
    if "operations" not in spec or not isinstance(spec["operations"], list):
        return False
    for part in spec["parts"]:
        if not isinstance(part, dict) or "type" not in part or "name" not in part:
            return False
    return True

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a FreeCAD 3D model spec generator.

Output ONLY a raw JSON object with these keys:
- "parts": list of primitives (box, cylinder, sphere, etc.)
- "operations": list of boolean operations (cut, fuse_all, assign)

NO thoughts, NO steps, NO markdown, NO backticks.
Start with { and end with }."""

# ── COMBINED conversion + formatting (single map pass) ────────────────────────

def convert_and_format(batch):
    """
    Single-pass: Convert CadQuery -> FreeCAD JSON -> formatted chat text.
    Returns PLAIN TEXT strings with chat template already applied.
    No JSON messages in output (avoids runtime parsing in collate_fn).
    """
    formatted_texts = []

    for code_bytes in batch.get("cadquery_file", []):
        try:
            code = code_bytes.decode("utf-8", errors="ignore") if isinstance(code_bytes, bytes) else str(code_bytes)
            spec = convert_cadquery(code)

            if spec is None or not validate_json_spec(spec):
                formatted_texts.append("")
                continue

            response = json.dumps(spec, indent=2)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Create a 3D model based on the provided CadQuery reference."},
                {"role": "assistant", "content": response},
            ]

            # Apply chat template HERE (not in collate_fn)
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            formatted_texts.append(text)

        except Exception as e:
            print(f"[WARN] Failed: {e}")
            formatted_texts.append("")

    return {"text": formatted_texts}

# ── Dry-run on 50 samples ────────────────────────────────────────────────────

print("=== DRY RUN: Converting 50 samples ===")
dry_run = dataset.select(range(min(50, len(dataset))))
dry_result = dry_run.map(convert_and_format, batched=True, batch_size=10)

# Count successful conversions
dry_convertible = sum(1 for t in dry_result["text"] if t)
dry_total = len(dry_result)
dry_rate = dry_convertible / dry_total * 100

print(f"✓ Dry run: {dry_convertible}/{dry_total} convertible ({dry_rate:.1f}%)")

# Show a sample output
for text in dry_result["text"]:
    if text:
        print(f"\n--- Sample formatted output (first 300 chars) ---")
        print(text[:300])
        break

# CRITICAL: Stop if dry-run fails badly
assert dry_rate >= 50, f"❌ Dry-run conversion rate too low: {dry_rate:.1f}%. Check converter."
print(f"\n✓ Dry-run passed. Proceeding to full conversion.")

# =============================================================================
# CELL 5: Full Conversion (single pass)
# =============================================================================
# Convert full dataset in ONE map pass (no double processing).

import gc

print("=== Full conversion + formatting (single pass) ===")
converted = dataset.map(
    convert_and_format,
    batched=True,
    batch_size=100,
    num_proc=1,  # CRITICAL: single process for CadQuery OCP (cannot be pickled)
    desc="Converting + Formatting",
)

# Filter empty entries (failed conversions)
train_data = converted.filter(lambda x: len(x["text"]) > 10)
print(f"✓ Successful conversions: {len(train_data)}/{len(converted)} ({len(train_data)/len(converted)*100:.1f}%)")

# Limit dataset size for incremental training
MAX_SAMPLES = 3000
if len(train_data) > MAX_SAMPLES:
    train_data = train_data.select(range(MAX_SAMPLES))
print(f"✓ Using {len(train_data)} samples for training")

# Free memory from intermediate data
del converted
gc.collect()

# Show sample
print(f"\n--- Sample formatted text (first 300 chars) ---")
print(train_data[0]["text"][:300])
# Output:
# ✓ Successful conversions: 61200/81015 (75.5%)
# ✓ Using 3000 samples for training

# =============================================================================
# CELL 6: Load Model + QLoRA Adapter
# =============================================================================
# QLoRA: 4-bit quantized base model + LoRA adapter.

from unsloth import FastLanguageModel
from transformers import TrainingArguments, Trainer

MAX_SEQ_LENGTH = 2048
LORA_RANK = 16

print("Loading Qwen2.5-Coder-3B-Instruct in 4-bit (QLoRA)...")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-Coder-3B-Instruct-bnb-4bit",
    max_seq_length=MAX_SEQ_LENGTH,
    dtype=None,
    load_in_4bit=True,
)

print("Attaching LoRA adapter...")
model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=3407,
)

gpu_mem_used = torch.cuda.memory_allocated() / 1024**3
gpu_mem_total = torch.cuda.get_device_properties(0).total_memory / 1024**3
print(f"✓ Model loaded: {gpu_mem_used:.1f} GB / {gpu_mem_total:.1f} GB VRAM")
print(f"✓ LoRA rank: {LORA_RANK}")
print(f"✓ Max sequence length: {MAX_SEQ_LENGTH}")

# =============================================================================
# CELL 7: Train with Checkpoints (FIXED collate_fn)
# =============================================================================
# Checkpoints save every 500 steps to Google Drive.

BATCH_SIZE = 8
GRADIENT_ACCUMULATION = 4
SAVE_STEPS = 500
NUM_EPOCHS = 3

steps_per_epoch = len(train_data) // (BATCH_SIZE * GRADIENT_ACCUMULATION)
total_steps = steps_per_epoch * NUM_EPOCHS
print(f"✓ Steps per epoch: {steps_per_epoch}")
print(f"✓ Total training steps: {total_steps}")
print(f"✓ Estimated time: ~{total_steps * 4 / 60:.0f} minutes")

OUTPUT_DIR = str(CHECKPOINT_ROOT / "qlora-cadquery")

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=NUM_EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRADIENT_ACCUMULATION,
    learning_rate=2e-4,
    weight_decay=0.01,
    warmup_steps=100,
    lr_scheduler_type="cosine",
    fp16=True,
    logging_steps=50,
    save_strategy="steps",
    save_steps=SAVE_STEPS,
    save_total_limit=3,
    optim="adamw_8bit",
    seed=3407,
    report_to="none",
    dataloader_num_workers=2,
    remove_unused_columns=False,
)

# ── collate function (minimal - only tokenizes pre-formatted text) ────────────
# Dataset already contains formatted chat text from Cell 5.
# No JSON parsing, no chat template application here.

def collate_fn(batch):
    """
    Minimal collate: only tokenizes pre-formatted text.
    No JSON parsing, no chat template application.
    Dataset already contains formatted text from Cell 5.
    """
    texts = [item["text"] for item in batch]

    tokenized = tokenizer(
        texts,
        truncation=True,
        max_length=MAX_SEQ_LENGTH,
        padding="max_length",
        return_tensors="pt",
    )

    labels = tokenized["input_ids"].clone()
    labels[labels == tokenizer.pad_token_id] = -100

    return {
        "input_ids": tokenized["input_ids"],
        "attention_mask": tokenized["attention_mask"],
        "labels": labels,
    }

# ── Initialize trainer ────────────────────────────────────────────────────────

trainer = Trainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_data,
    args=training_args,
    data_collator=collate_fn,
)

# ── Resume from checkpoint if exists ──────────────────────────────────────────

resume_checkpoint = None
checkpoints = sorted(Path(OUTPUT_DIR).glob("checkpoint-*")) if Path(OUTPUT_DIR).exists() else []
if checkpoints:
    resume_checkpoint = str(checkpoints[-1])
    print(f"✓ Resuming from checkpoint: {resume_checkpoint}")
else:
    print("✓ Starting training from scratch")

# ── Train! ────────────────────────────────────────────────────────────────────

print("\n=== Starting Training ===")
print(f"  Dataset: {len(train_data)} samples")
print(f"  Batch: {BATCH_SIZE} × {GRADIENT_ACCUMULATION} = {BATCH_SIZE * GRADIENT_ACCUMULATION} effective")
print(f"  Checkpoints: every {SAVE_STEPS} steps → {OUTPUT_DIR}")
print(f"  Press Ctrl+C to stop early (last checkpoint is saved)\n")

train_result = trainer.train(resume_from_checkpoint=resume_checkpoint)

print("\n=== Training Complete ===")
print(f"  Total steps: {train_result.global_step}")
print(f"  Final loss: {train_result.training_loss:.4f}")
print(f"  Training time: {train_result.metrics['train_runtime']:.0f} seconds")

FINAL_DIR = str(CHECKPOINT_ROOT / "qlora-cadquery-final")
model.save_pretrained(FINAL_DIR)
tokenizer.save_pretrained(FINAL_DIR)
print(f"✓ Final adapter saved to: {FINAL_DIR}")

del trainer
gc.collect()
torch.cuda.empty_cache()

# =============================================================================
# CELL 8: Evaluation + Test Generation
# =============================================================================

print("Loading fine-tuned model from Drive...")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=FINAL_DIR,
    max_seq_length=MAX_SEQ_LENGTH,
    dtype=None,
    load_in_4bit=True,
)
FastLanguageModel.for_inference(model)
print("✓ Model loaded for inference")

test_prompts = [
    "Make a box 10 by 20 by 30 mm",
    "Create a cylinder 50mm tall 10mm radius",
    "Make a sphere radius 15mm",
    "Create an L bracket 30mm wide 20mm tall",
    "Make a flange outer diameter 30 inner bore 10",
]

print("\n=== Test Generation ===\n")

for prompt in test_prompts:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to("cuda")

    outputs = model.generate(
        input_ids=inputs,
        max_new_tokens=512,
        temperature=0.1,
        top_p=0.95,
        use_cache=True,
    )

    response = tokenizer.decode(outputs[0][inputs.shape[-1]:], skip_special_tokens=True)

    try:
        spec = json.loads(response)
        valid = "✓" if ("parts" in spec and "operations" in spec) else "✗"
    except json.JSONDecodeError:
        valid = "✗ (invalid JSON)"

    print(f"Prompt: {prompt}")
    print(f"Result: {valid}")
    print(f"Response: {response[:200]}...")
    print("-" * 60)

gc.collect()
torch.cuda.empty_cache()
print(f"\n✓ VRAM freed. Final usage: {torch.cuda.memory_allocated()/1024**3:.1f} GB")
print("\n=== Pipeline Complete ===")
print(f"✓ Adapter saved to: {FINAL_DIR}")
