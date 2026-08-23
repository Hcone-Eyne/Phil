# Coding Standards — CadQuery→FreeCAD Conversion & Colab Fine-Tune Pipeline

Feed this to opencode as a system/instruction file before it generates any code for this task. It covers the conversion script (63K CadQuery samples → FreeCAD JSON specs) and the Colab fine-tuning run.

---

## 1. No raw Python loops over data — vectorize or batch

**Banned pattern:**
```python
results = []
for sample in dataset:
    converted = convert(sample)
    results.append(converted)
```

**Required pattern — use one of these instead:**

- **Pandas/vectorized ops** for anything tabular (filtering, column transforms, dedup):
  ```python
  df["convertible"] = df["op_type"].isin(SUPPORTED_OPS)
  convertible_df = df[df["convertible"]]
  ```
- **`multiprocessing.Pool` / `concurrent.futures`** for per-sample work that can't be vectorized (each CadQuery file needs independent parsing/conversion — this is embarrassingly parallel):
  ```python
  from concurrent.futures import ProcessPoolExecutor
  with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
      results = list(ex.map(convert_one, sample_paths, chunksize=50))
  ```
- **`datasets.map(..., batched=True, num_proc=N)`** if using HuggingFace `datasets` — this is the standard for 63K-scale transforms and handles batching/parallelism for you:
  ```python
  ds = ds.map(convert_batch, batched=True, batch_size=256, num_proc=4)
  ```
- **`.apply()` is still a disguised Python loop** — don't use it as a substitute for vectorization; only acceptable inside `ProcessPoolExecutor.map` as the unit of work.

Exception: loops over ≤5 static config items (op names, file paths you already enumerated) are fine — the rule is about the 63K-scale data path, not every `for` statement in existence.

## 2. Colab free-tier constraints — design around them, don't discover them at runtime

Free tier = T4 GPU (16GB VRAM), ~12GB system RAM, session kill after ~12hrs or ~90min idle, disk resets on disconnect.

- **Never load the full 63K/100K dataset into RAM as Python objects at once.** Stream from disk or use `datasets` with `streaming=True` / memory-mapped arrow files.
- **Batch size:** default to 4–8 for fine-tuning on T4 with a small (≤3B) model; use gradient accumulation (`gradient_accumulation_steps=4–8`) to simulate a larger effective batch instead of raising batch size and OOMing.
- **Use `fp16`/`bf16` mixed precision** (`torch.cuda.amp` or `Trainer(fp16=True)`) — T4 does not have enough VRAM for fp32 fine-tuning at any useful batch size.
- **Mount Google Drive at the start of every notebook run** (`from google.colab import drive; drive.mount('/content/drive')`) — local `/content` disk is wiped on disconnect, Drive is not.
- **Free the CadQuery/FreeCAD conversion intermediate files** (`del obj; gc.collect(); torch.cuda.empty_cache()`) between the conversion phase and the training phase — don't let both live in memory in the same session.

## 3. No silent bugs — fail loud, validate early

- Every conversion function gets a **schema validation step** before the result is counted as "convertible" — validate the output JSON against Phil's existing builder.py spec (the same one your self-correction loop uses), not just "did CadQuery parse without throwing."
- **No bare `except:` or `except Exception: pass`.** Every catch block logs the sample ID, the op type, and the exception — you need this to know *why* the ~22% non-convertible rate happens, and to catch new failure modes without silently dropping samples.
- **Assert shapes/types at function boundaries** for anything feeding the model (tensor shapes, tokenized lengths) — an assert that fires in dev is cheaper than a shape mismatch that fires 40 minutes into a Colab training run.
- **Dry-run on 50 samples before the full 63K pass.** Every conversion script run starts with a `--limit 50` flag default, expanded only after a human checks the sample outputs.

## 4. Checkpointing — assume the session dies mid-run

Colab free tier *will* disconnect you mid-run. Design for it from the first line of code, not as a recovery afterthought.

- **Conversion phase:** write converted samples incrementally to disk (e.g. append to a JSONL file, or write one shard every 1,000 samples) — never hold all 63K converted results in memory until a final `save()` at the end. On restart, skip samples already present in the output file (check by sample ID).
  ```python
  OUT = "/content/drive/MyDrive/phil-cad/converted.jsonl"
  done_ids = load_done_ids(OUT)  # read existing file, get already-processed IDs
  with open(OUT, "a") as f:
      for sample in dataset:
          if sample["id"] in done_ids:
              continue
          result = convert_one(sample)
          f.write(json.dumps(result) + "\n")
          f.flush()
  ```
- **Training phase:** use `Trainer(save_strategy="steps", save_steps=200, save_total_limit=3, output_dir="/content/drive/MyDrive/phil-cad/checkpoints")` — save to Drive, not local disk, and resume with `resume_from_checkpoint=True` so a killed session picks back up instead of restarting from step 0.
- **Log to a file on Drive too**, not just stdout — Colab's output buffer is not something you can recover after a disconnect.

## 5. Quick pre-flight checklist for opencode to self-check before returning code

- [ ] No `for` loop touching the 63K/100K dataset directly — parallelized or vectorized
- [ ] Batch size + fp16 + gradient accumulation set for T4/16GB
- [ ] Drive mounted, all persistent writes go to Drive not `/content`
- [ ] Every except block logs sample ID + reason, none are silent
- [ ] Incremental JSONL writes with resume-by-ID for conversion
- [ ] `save_steps` + `resume_from_checkpoint` set for training
- [ ] Dry-run flag defaults to a small sample count
