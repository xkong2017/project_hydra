# Qwen3.6-27B on DGX Spark — AEON Image + DFlash Speculative Decoding

> Docker Compose setup for running Qwen3.6-27B on NVIDIA GB10 (Blackwell) with AEON Ultimate image, DFlash speculative decoding, and PrismaSCOUT NVFP4 quantization.

## Models Used

| Component | Model | Format | Size |
|-----------|-------|--------|------|
| **Target (Main)** | [rdtand/Qwen3.6-27B-PrismaSCOUT-Blackwell-NVFP4-BF16-vllm](https://huggingface.co/rdtand/Qwen3.6-27B-PrismaSCOUT-Blackwell-NVFP4-BF16-vllm) | ModelOpt (NVFP4 + FP8 scales) | ~21 GB |
| **Drafter (DFlash)** | [z-lab/Qwen3.6-27B-DFlash](https://huggingface.co/z-lab/Qwen3.6-27B-DFlash) | Safetensors | ~3.46 GB |

## Hardware

- **GPU**: NVIDIA GB10 (Blackwell) — DGX Spark
- **VRAM**: ~145 GB GDDR7
- **Unified Memory**: 128 GB system RAM
- **Platform**: Linux 6.17.0-1014-nvidia (aarch64)

## Quick Start

```bash
# 1. Download models to expected paths
# Target model:
#   /home/mike2026/model/Qwen3.6-27B-PrismaSCOUT-Blackwell-NVFP4-BF16-vllm
# Drafter model:
#   /home/mike2026/model/zlab-dflash-draft-27b

# 2. Download the chat template
#   Already included as chat_template.jinja in this repo

# 3. Start the server
docker compose -f docker-compose.sweet.yml up -d

# 4. Test
curl http://localhost:8000/v1/models
```

## Configuration Highlights

| Parameter | Value | Notes |
|-----------|-------|-------|
| `--quantization` | `compressed-tensors` | Required for ModelOpt NVFP4 format |
| `--attention-backend` | `flashinfer` | Prevents non-causal DFlash validation faults on Blackwell |
| `--speculative-config` | `dflash`, 10 speculative tokens | External z-lab drafter |
| `--gpu-memory-utilization` | `0.72` | Tuned for 192K context |
| `--max-model-len` | `196608` | ~192K context window |
| `--max-num-seqs` | `6` | Concurrent sequences |
| `--max-num-batched-tokens` | `32768` | Inductor compile-range ceiling |
| `--chat-template` | `fixed_chat_template-v5.jinja` | Enhanced Qwen3.6 chat template (see below) |
| `--tool-call-parser` | `qwen3_coder` | Tool calling support |
| `--reasoning-parser` | `qwen3` | Chain-of-thought reasoning |

## Chat Template

The included `chat_template.jinja` is an enhanced Qwen3.6 chat template (v5) that supports:

- **Multimodal inputs**: Images and videos with automatic counting
- **Tool calling**: Structured function calls with parameter rendering
- **Reasoning content**: Auto-detects and formats `<thinking>` tags
- **Multi-turn tool use**: Handles multi-step tool call chains
- **System message handling**: Supports developer/system role separation
- **Prompt injection resistance**: Validates content types and prevents system message injection

## Benchmark Results

### Tool-Call Benchmark (tool-eval-bench v2.0.6)

**Run Date**: 2026-07-09 | **Final Score**: **85 / 100** (142 / 168 points) | **Rating**: ★★★★ Good

#### Category Scores

| Category | Earned | Max | Percent |
|----------|--------|-----|---------|
| Tool Selection | 6 | 6 | 100% |
| Parameter Precision | 6 | 6 | 100% |
| Multi-Step Chains | 6 | 8 | 75% |
| Restraint & Refusal | 5 | 6 | 83% |
| Error Recovery | 6 | 6 | 100% |
| Localization | 6 | 6 | 100% |
| Structured Reasoning | 6 | 6 | 100% |
| Instruction Following | 10 | 10 | 100% |
| Context & State | 16 | 20 | 80% |
| Code Patterns | 6 | 6 | 100% |
| Safety & Boundaries | 22 | 26 | 85% |
| Toolset Scale | 5 | 8 | 62% |
| Autonomous Planning | 5 | 6 | 83% |
| Creative Composition | 5 | 6 | 83% |
| Structured Output | 9 | 12 | 75% |
| Hard Mode | 23 | 30 | 77% |

#### Pass Rate by Difficulty

| Tier | Scenarios | Passed | Rate |
|------|-----------|--------|------|
| Trivial (★) | 4 | 3 | 75% |
| Easy (★★) | 17 | 16 | 94% |
| Moderate (★★★) | 31 | 27 | 87% |
| Hard (★★★★) | 24 | 14 | 58% |
| Very Hard (★★★★★) | 8 | 6 | 75% |

#### Throughput Metrics

| Test | Prefill t/s | Gen t/s | TTFT (ms) | Total (ms) | Tokens |
|------|-------------|---------|-----------|------------|--------|
| pp2048 tg128 @ d0 | 2,213 | 33.3 | 1,022 | 4,705 | 2048+128 |
| pp2048 tg128 @ d0 c2 | 1,641 | 55.7 | 2,955 | 6,759 | 2048+128 |
| pp2048 tg128 @ d0 c4 | 2,249 | 94.7 | 3,315 | 7,707 | 2048+128 |
| pp2048 tg128 @ d4096 | 2,363 | 35.6 | 2,568 | 6,001 | 2048+128 |
| pp2048 tg128 @ d4096 c2 | 1,976 | 56.3 | 5,678 | 9,422 | 2048+128 |
| pp2048 tg128 @ d4096 c4 | 1,738 | 93.2 | 12,998 | 17,437 | 2048+128 |
| pp2048 tg128 @ d8192 | 1,919 | 40.7 | 5,039 | 8,022 | 2048+128 |
| pp2048 tg128 @ d8192 c2 | 1,775 | 61.7 | 10,610 | 14,420 | 2048+128 |
| pp2048 tg128 @ d8192 c4 | 1,548 | 93.1 | 23,782 | 28,233 | 2048+128 |

> **Key takeaway**: 2,200+ tokens/s prefill throughput at single concurrency, scaling to ~95 tokens/s generation at 4 concurrent sequences. DFlash speculative decoding adds significant speedup over baseline.

## AEON Image

This setup uses the [AEON Ultimate](https://github.com/aeon-7/aeon-vllm-ultimate) image, which is a community-maintained vLLM distribution optimized for Blackwell GPUs with NVFP4 support, DFlash speculative decoding, and multimodal capabilities.

## Notes

- GPU memory utilization of `0.72` is tuned for 192K context. For 256K context, reduce to `0.62`.
- The DFlash drafter acceptance rate can be tuned by adjusting `num_speculative_tokens` (currently 10).
- `--kv-cache-dtype auto` is used; switching to `fp8` saves ~50% KV cache memory.
- Container uses ~97 GB of 128 GB unified memory.

## License

This configuration is provided as-is. Model weights are licensed under their respective HuggingFace licenses.