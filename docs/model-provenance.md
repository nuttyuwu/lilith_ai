# Verified model provenance — 2026-10-13

Local deployed file: models/Lilith_AI_8B_Q4_0.gguf
SHA256: 60b069b8b24c54b8be2909595dbf27077a260535eb47435fd0702eae77d24dfa
Matches the publisher's Hugging Face LFS SHA256 exactly.
Publisher repository: CMM7590/Lilith_AI_8B
Pinned revision: 3b594a5d27c27a841e57e6a6c7938b303df4f099

The publisher explicitly identifies Sao10K/Llama-3.1-8B-Stheno-v3.4 as the base for its Lilith LoRA, trained on original game dialogue.
Verified base repository current revision: 423b189861eb2ee8ec01cf3066aa10159d0c33a0
The base repository includes nine BF16 safetensors shards, config.json, tokenizer.json, tokenizer_config.json and special_tokens_map.json. This is a discoverable training checkpoint, unlike the deployed quantization.

Important distinction: Stheno is the pre-Lilith base. The publisher does not expose a separate Lilith PEFT adapter or merged safetensors checkpoint in this repository. Its F16 file is still GGUF. The exact historical Stheno revision used for the original Lilith training is not stated. Training a new Mira adapter on the verified Stheno checkpoint would produce a new model; do not assume it can be attached unchanged to the existing Lilith GGUF.

Sources inspected:
- https://huggingface.co/CMM7590/Lilith_AI_8B
- https://huggingface.co/api/models/CMM7590/Lilith_AI_8B?blobs=true
- https://huggingface.co/Sao10K/Llama-3.1-8B-Stheno-v3.4
- https://huggingface.co/api/models/Sao10K/Llama-3.1-8B-Stheno-v3.4

No weights downloaded or trained. No live settings modified.
