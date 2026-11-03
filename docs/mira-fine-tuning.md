# Testing and fine-tuning Mira

## Start with measured failures

The deployed model is `Lilith_AI_8B_Q4_0.gguf`, a quantized 8B inference file.
Its metadata says `Merged_Hf`, architecture `llama`, and provides no original
base checkpoint identity. Publisher research now identifies Stheno v3.4 as the pre-Lilith base; see [verified provenance](model-provenance.md). A separate Lilith adapter/merged safetensors checkpoint is not published. Do not guess an adapter-compatible model from its
filename. The PC has an RTX 3060 Laptop GPU with 6144 MiB VRAM, verified with
`nvidia-smi`.

The live configuration uses temperature 0.85; earlier character probes used
0.4. That is a confounding difference, not evidence that a prompt change alone
improved the model. The batch tool defaults to actual configured temperature
without changing `config.ini`. Each test uses an independent temporary room;
optional context must be supplied explicitly. Reports include actual generation
requests, raw output, expressions, timings, and configuration. Automatic echo,
punctuation, and emotion flags are diagnostics, not a personality-quality score.

## Run your own batches

Edit `C:\Lilith\Mira Questions.txt`: one question per line. Empty lines and
lines starting with `#` are ignored. Double-click `C:\Lilith\Test Mira.bat`.
The completed HTML review opens in your browser, and matching CSV/JSON files
are saved in a unique `audit/batch-runs/` directory entry. Completed questions
are checkpointed so Ctrl+C does not lose earlier results. These reports contain
the personality prompt and test questions; they remain outside the public
static site and are ignored by Git.

From the project folder:

```powershell
venv\Scripts\python.exe batch_test.py "C:\Lilith\Mira Questions.txt" --validate-only
venv\Scripts\python.exe batch_test.py "C:\Lilith\Mira Questions.txt" --mode both --limit 10
venv\Scripts\python.exe batch_test.py "C:\Lilith\Mira Questions.txt" --temperature 0.4 --repeat 3
venv\Scripts\python.exe batch_test.py examples/batch_questions.jsonl --mode soft
```

TXT accepts ordinary questions. JSONL or a JSON array also supports objects
with `id`, `question`, `mode`, `context` (user/assistant turns),
`expected_emotions`, and optional `ideal_reply`. A CLI mode overrides input modes.
`--mode both` compares every question in both modes. CPU inference is the
default to avoid another copy of the model competing with the hosted app for
GPU memory. `--use-gpu` opts into the configured GPU layers. HTTP backends still
use their configured provider. No personal conversations are loaded.

## Build human-approved training data

Review the CSV after a run finishes. Fill `rating` (your own score),
`ideal_reply` (your corrected Mira response), and `ideal_emotion` (desired
expression). Set `approved` to `yes` only for examples you want trained.
If the generated answer is good, explicitly copy it into `ideal_reply`.
An unreviewed model response is never automatically promoted into training data.

```powershell
venv\Scripts\python.exe batch_test.py --export-training "audit/batch-runs/YOUR-RUN.csv" --training-output "audit/mira-approved-training.jsonl"
```

Only approved, nonempty corrections are exported. The dataset uses the actual
system/context/user messages and a final assistant JSON dialogue/emotion object
for structured runs. Legacy Lilith runs preserve their tagged output contract;
character/format metadata is checked before export.
Keep evaluation questions and conversational scenarios separate from training
examples to detect memorization. Split by scenario/conversation, not neighboring
turns from the same conversation. Do not train the existing echoing, boilerplate,
off-topic jokes, or unwanted apologies back into the model.

As a starting experiment, curate roughly 200–500 varied examples covering
ordinary conversation, disagreement, humor with appropriate cues, uncertain
emotions, both temperaments, and context continuity. This is a working target,
not a guarantee. Prefer a smaller reviewed collection over many synthetic
answers. Keep a fixed held-out set and judge relevance, natural voice,
independence, memory/context use, expression fit, and repetition manually.

## Actual model training

1. Obtain the exact original Hugging Face checkpoint and tokenizer/model card,
   or choose a documented replacement checkpoint deliberately. Our current
   GGUF alone does not supply the source checkpoint needed for this workflow.
2. Establish a baseline using this batch suite and temperature comparisons.
   Also compare a concise stable persona against the full prompt: long,
   conflicting instructions can obscure the target behavior. Do not confuse
   lower temperature with learned personality.
3. Use supervised fine-tuning with a LoRA/QLoRA adapter on the Hugging Face
   checkpoint. [TRL's SFTTrainer](https://huggingface.co/docs/trl/main/sft_trainer)
   supports conversational datasets; [PEFT integration](https://huggingface.co/docs/trl/main/peft_integration)
   documents LoRA/QLoRA training. Train assistant targets with the checkpoint's
   own chat template. Check tokenized sample lengths before choosing sequence
   length: our captured full-persona prompts may be long.
4. A 6 GB GPU does not establish that an 8B training job will fit. Fit depends
   on sequence length, optimizer, attention implementation, and batch size.
   A smaller compatible model or a larger training GPU may be more practical.
   No paid GPU job or model download has been started by this change.
5. Evaluate the adapter on the held-out batches with the same sampling settings.
   Keep the old model for rollback. The [llama.cpp adapter converter](https://github.com/ggml-org/llama.cpp/blob/master/convert_lora_to_gguf.py)
   converts supported Hugging Face PEFT adapters to GGUF; conversion/loading must
   match the actual base model and architecture. Alternatively merge with its
   base checkpoint and convert/quantize the resulting model for deployment.

Training has not been started. The publisher identifies Stheno v3.4 as the pre-Lilith base (see model-provenance.md); deciding whether to train a fresh Mira model on that base and collecting
approved examples are the concrete next steps; adding more personality text
alone is not fine-tuning model weights.
