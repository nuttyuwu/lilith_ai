# Mira prompt experiments

The live Mira persona is unchanged: the tested shorter prompts did not reliably satisfy the coherence and temperament checks. The original is archived at audit/prompt-refresh/mira-persona.original.txt; three candidates are stored alongside it. Read the result comparison before choosing one.

## Reproduce a comparison

Run from the project directory:

```powershell
.\venv\Scripts\python.exe batch_test.py examples\mira_prompt_regression.jsonl --persona audit/prompt-refresh/mira-persona.original.txt --mode both --temperature 0.85 --output audit/prompt-refresh/recheck-original
.\venv\Scripts\python.exe batch_test.py examples\mira_prompt_regression.jsonl --persona audit/prompt-refresh/mira-persona.focused.txt --mode both --temperature 0.4 --output audit/prompt-refresh/recheck-focused
```

The --persona option validates the file before loading the model, overrides only the disposable test configuration, and records its path and SHA256. It does not edit config.ini or the live persona.

## Review criteria

The twelve scenarios test greetings, invitations, missed plans, independent disagreement, jokes, speaker tracking, repairs, remembered plans, ordinary family context, joke clarification, explicit boundaries, and topic changes. Follow-up tests supply explicit user/assistant history; these are seeded-history tests, not proof that an autonomous multi-turn conversation will remain coherent.

A complete speaker answer must say Khongor/user was gaming and Mira was waiting. A remembered-plan answer must preserve Adventure Time, tomorrow, and 8. Jealous protests must refer to the actual event and match the expression. Respecting space is required in both modes. Ordinary family context must not become an invented romantic rival. Brief casual dialogue is allowed, but irrelevant stock replies are not a successful answer.

These cases were used to diagnose and iterate prompts, so they are a development suite, not a held-out evaluation set. Create independent scenarios before measuring any future training improvement. Single sampled replies per scenario/mode do not establish statistical superiority.

## Correction drafts

examples/mira_correction_drafts.json contains 24 proposed targets, all approved=false. They are authored examples for review, not verified historical dialogue. Correct wording and expressions to match your intended character. No model-generated response or draft has been exported as approved training data.

The existing batch CSV supports ideal_reply, ideal_emotion, and approved. Training export only includes rows explicitly marked yes after review. Existing Lilith model weights and personal history remain unchanged.

## Next model experiment

The published pre-Lilith base is Sao10K/Llama-3.1-8B-Stheno-v3.4. Before fine-tuning, compare that base against the current Lilith-specific model using the same suite, then choose the checkpoint and assemble reviewed corrections with a separate held-out set. The publisher does not provide its Lilith adapter separately. Current prompt failures do not prove that fine-tuning, or a different base, will fix them without evaluation.
