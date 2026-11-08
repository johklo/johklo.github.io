---
title: "09. Text-to-Image Generation with Diffusion"
description: "A detailed study of a text-conditioned diffusion system: caption repair, latent U-Net and DiT denoisers, noise-prediction training, guidance and fast samplers, alignment metrics, GPU sizing, and a safety-wrapped serving pipeline"
date: 2026-11-08T18:00:00+09:00
lastmod: 2026-11-08T20:30:00+09:00
weight: 90
draft: false
tags: ["book-club", "genai-system-design", "diffusion-models", "text-to-image", "ai-safety"]
---
A user types up to about 128 words describing a scene and, within roughly ten seconds, gets back a 1024 by 1024 image that looks good and contains what was asked for: the right objects, counts, colors, layout and style. The face generator in an earlier chapter started from noise with no user control. Here language steers content, which brings three new problems. The model has to read long, compositional prompts and respect every clause. The system has to refuse some requests and catch unsafe outputs from harmless prompts. And the generator is a multi-billion-parameter network that runs tens of sequential passes per image, so every quality gain shows up on the GPU bill.

The core tension is a triangle. **Fidelity** (realism plus prompt adherence) pulls toward bigger models, more steps and stronger guidance. **Latency and cost** pull toward fewer steps, distilled models and smaller tensors. **Safety and fairness** add classifiers before and after generation and constrain the training data. Most decisions below move a point inside that triangle; a good answer names which corner each one gives up.

## Requirements that change the design

Functional: English prompts up to 128 words (about 160 to 200 tokens), other languages later; one to four 1024px images per request across photos, portraits, illustration and abstract art; training on roughly 500M user-asset images whose captions vary in quality; no sexual, violent or hateful imagery; outputs audited for skew in age, gender and skin tone when the prompt leaves them unspecified.

Non-functional: about 10 seconds at p95 for the batch; bounded GPU-seconds per image, because unhappy users reroll and every reroll costs as much as the first try; regular retraining without breaking the safety stack.

| Requirement | Design consequence | If relaxed |
|---|---|---|
| 1024px output | Generate in a compressed latent, or at 64px plus an upsampling cascade | At 256px one pixel-space model is fine |
| Long, detailed prompts | T5-class text encoder with a 256-token context, not only CLIP's 77 | A CLIP text tower suffices |
| English now, more later | Swappable text encoder; embeddings versioned per encoder | Multilingual from day one costs some English quality |
| Noisy captions | Recaption with a vision-language model, filter by image-text similarity | Skip the captioning cluster |
| 10 s p95 | 20 to 30 solver steps, latent space, low precision, batched samples | 60 s allows pixel cascades and 100+ steps |
| Fairness on three attributes | Attribute stats in data and eval; diversify unspecified attributes | Outputs mirror the web's skew |
| Disallowed content | Data filters, prompt classifier, output classifier, watermark | An internal tool might keep only output checks |

## Framing as an ML task

The task is conditional generation: learn \( p(x \mid c) \) for image \(x\) and prompt \(c\), then sample from it. Input is a string, output a pixel tensor, and there is no single correct answer. Training uses image-caption pairs as samples from the joint distribution.

| Family | Generation | Detail at 1024px | Speed knob | Training signal | Main weakness |
|---|---|---|---|---|---|
| Autoregressive image tokens (DALL-E 1, Parti) | Transformer emits VQ tokens one by one | Good, capped by tokenizer | Almost none | Every token, one pass | Thousands of sequential steps |
| Masked tokens (Muse) | Fill masked tokens in 10 to 20 parallel rounds | Good | Rounds | Many tokens per pass | Tokenizer cap, fewer recipes |
| Diffusion, pixel or latent (Imagen, Stable Diffusion, DALL-E 2 and 3) | Iteratively denoise Gaussian noise | Best in practice | Steps, solver, guidance | One noise level per example | Many network calls per image |
| GAN (GigaGAN) | One generator pass | Good, weaker composition | Already one step | Adversarial | Unstable at scale, mode collapse |

I would pick latent diffusion. It wins on visible detail, and its step count is a dial on one set of weights: the same model can serve a two-second draft and a ten-second final. Autoregressive models train more efficiently (every token is supervised per pass, while diffusion supervises one noise level per sample) and reuse LLM infrastructure, a strong argument for a unified chat-and-draw assistant but not for a dedicated service with a hard latency target. GANs are fastest but scale poorly on compositional prompts, and distillation lets diffusion recover most of that speed anyway.

## Data

### Sources and consent

Confirm the license allows training, honor opt-outs and deletions, and record per-image provenance so a removal can be traced to every shard and model. Logged prompts, generations and feedback are useful for preference tuning and eval sets, but cap generated images in pretraining: a generator trained on its own outputs narrows its distribution over rounds.

### Image filtering

- **Resolution floor.** Around 256px short side for high-resolution stages, lower for early low-resolution pretraining. Upscaled thumbnails teach blur.
- **Deduplication.** File hashes for exact copies; perceptual hashes or embedding clusters with a cosine threshold near 0.95 for near copies. Duplicates over-weight popular images and drive memorization, a quality and legal risk.
- **Safety.** NSFW, gore and hate-symbol classifiers, with per-category thresholds audited by hand so benign images of people are not discarded wholesale.
- **Aesthetics.** A small regressor on CLIP image embeddings predicts human ratings. The threshold shapes the model's default style, so it is a product decision.
- **Junk.** Text-dominated images (by OCR coverage), screenshots, heavy watermarks. If many training images carry watermarks, the model learns to draw them.

### Caption repair

The model only learns concepts its captions mention. User captions are often absent, foreign-language, filenames or tag lists. Run a vision-language captioner (BLIP-family or larger) on every image to get dense descriptions of objects, attributes, counts, positions, style and visible text. Score the original caption with CLIP similarity; keep it when relevant because it carries proper nouns and user vocabulary, replace it when weak, and drop pairs still below a floor. Train on a mix of dense synthetic and short original captions. The [DALL-E 3 report](https://cdn.openai.com/papers/dall-e-3.pdf) found prompt following rises sharply with a high synthetic share, while a model trained only on long captions handles terse prompts poorly, which is why serving rewrites prompts. Captioner hallucinations are the main hazard: an object named but absent teaches the model to ignore words.

### Fairness and preprocessing

Run attribute classifiers on images with people and log distributions per role word ("nurse", "CEO") in the captions. Rebalance with sampling weights rather than deletion; it is cheap and reversible. Validate those classifiers on hand-labeled data, since their errors are themselves skewed.

Square center crops cut off heads and teach the model to center everything. Aspect-ratio bucketing (a handful of resolutions such as 1024x1024, 1152x896, 896x1152, batched within bucket) avoids that and enables non-square outputs. Pixels go to \([-1, 1]\) to match the noise scale. Each image passes once through the frozen autoencoder and is stored as a latent in tar or Parquet shards with metadata columns (scores, attributes, license, flags) so later stages can re-filter without reprocessing.

**Worked example: caching cost for 500M pairs.** A 1024px image in an 8x, 4-channel latent is \(128 \times 128 \times 4 = 65{,}536\) values, 128 KB in fp16, so about 64 TB in total. T5-XXL token embeddings are 4,096-wide: at 120 real tokens in bf16, \(120 \times 4096 \times 2 \approx 0.98\) MB per caption, close to 490 TB. So many teams cache latents but compute text embeddings online (roughly 10 to 20 percent more step time), or cache them only for the smaller high-resolution subset, or in fp8.

```mermaid
flowchart LR
  accTitle: Training data pipeline for text-to-image
  accDescr: User assets and logged product data pass license checks, image filters, deduplication, caption repair and fairness weighting, then aspect bucketing and frozen encoders produce latents and optional text embeddings written to sharded storage. Logged data mainly feeds preference and evaluation sets.
  A[("User assets, 500M pairs")] --> L["License and opt-out check"]
  F[("Logged prompts, outputs, feedback")] --> T["Tag provenance, cap share"]
  L --> IF["Filters: size, NSFW, aesthetic, text, watermark"]
  IF --> DD["Exact and near-duplicate removal"]
  DD --> CR["Caption repair: VLM plus CLIP scoring"]
  CR --> FA["Attribute stats and sample weights"]
  FA --> PP["Aspect buckets, normalize"]
  PP --> VAE["Frozen autoencoder to latents"]
  PP --> TXT["Text encoder, optional cache"]
  VAE --> S[("Sharded storage with metadata")]
  TXT --> S
  T --> PREF[("Preference and eval sets")]
```

Pitfalls: over-aggressive face filtering degrades portraits, aesthetic filters skew toward one look, and a hallucinating captioner spreads its errors everywhere.

## Model architecture

Four parts: a frozen text encoder, a frozen autoencoder between pixels and latents, a trainable denoiser in latent space, and optionally an upscaler.

**Text encoder.** CLIP's text tower is visually grounded but limited to 77 tokens and weak on word order. T5-XXL (about 4.7B encoder parameters) reads long prompts and handles syntax and negation better; Imagen found scaling the text encoder helped adherence more than scaling the image model. Many systems concatenate both. Keep it frozen so cached embeddings stay valid.

**Autoencoder.** A convolutional VAE maps \(1024 \times 1024 \times 3\) to \(128 \times 128 \times c\), \(c\) of 4 or 16. The input to every denoising step shrinks by \(3{,}145{,}728 / 65{,}536 = 48\) times, the largest single saving in the design. Latent channels cap fine detail; small text and faces need 16.

### U-Net denoiser

The U-Net halves spatial size and widens channels per level on the way down, mirrors that on the way up, and passes skip connections across so high-frequency detail survives. Each level stacks residual conv blocks; lower levels add self-attention and cross-attention to text.

```mermaid
flowchart TB
  accTitle: Text-conditioned U-Net denoiser in latent space
  accDescr: A noisy latent goes through three downsampling levels with residual blocks and attention, a bottleneck, and three mirrored upsampling levels joined by skip connections, ending in a predicted noise map of the same shape. The timestep embedding modulates residual blocks and text token embeddings supply keys and values for cross-attention.
  ZT["Noisy latent z_t, 128x128x4"] --> D1["Down 1: ResBlocks, 128x128, 320 ch"]
  D1 --> D2["Down 2: ResBlocks + attention, 64x64, 640 ch"]
  D2 --> D3["Down 3: ResBlocks + attention, 32x32, 1280 ch"]
  D3 --> MID["Bottleneck: ResBlock, self-attn, cross-attn"]
  MID --> U3["Up 3: ResBlocks + attention, 32x32"]
  U3 --> U2["Up 2: ResBlocks + attention, 64x64"]
  U2 --> U1["Up 1: ResBlocks, 128x128"]
  U1 --> OUT["Predicted noise, 128x128x4"]
  D1 -. skip .-> U1
  D2 -. skip .-> U2
  D3 -. skip .-> U3
  TS["Timestep t: sinusoidal + MLP"] --> MOD["Scale and shift in every ResBlock"]
  TX["Text tokens from T5 or CLIP"] --> CA["Keys and values for cross-attention"]
  MOD -.-> MID
  CA -.-> MID
```

Cross-attention is where language touches pixels. Flatten a feature map into \(N = h \times w\) vectors as queries; the \(M\) text token embeddings supply keys and values:

$$
\mathrm{CrossAttn}(H, E) = \mathrm{softmax}\!\left(\frac{(H W_Q)(E W_K)^\top}{\sqrt{d}}\right) E W_V
$$

\(H \in \mathbb{R}^{N \times d_h}\) are image features, \(E \in \mathbb{R}^{M \times d_e}\) text embeddings, \(W_Q, W_K, W_V\) project both to width \(d\), and each softmax row is one spatial position's distribution over prompt tokens. Averaging those maps per token shows where "red" or "cat" lands, which editing methods such as prompt-to-prompt exploit.

The timestep is embedded with sinusoids and an MLP, then scales and shifts normalized activations in each residual block. Without it the network cannot tell light noise from near-total noise, and the correct action differs a lot. Group or layer norm is preferred over batch norm because per-sample statistics behave better with small per-GPU batches whose noise levels vary.

### DiT alternative

A Diffusion Transformer patchifies the latent (patch 2 turns \(128 \times 128\) into 4,096 tokens), adds 2D position embeddings, runs a Transformer stack, and unpatchifies back to a noise map. Timestep and pooled text modulate each block via adaptive layer norm; the full text enters by cross-attention or, in Stable Diffusion 3's MM-DiT, by joint attention over concatenated text and image tokens. DiTs scale predictably with compute ([Peebles and Xie](https://arxiv.org/abs/2212.09748)), reuse LLM kernels and parallelism, and treat aspect ratios as variable token counts; U-Nets converge faster on small budgets. Patch 1 instead of 2 means 4x the tokens and about 16x the attention cost. For a new large build I would choose DiT.

**Upscaling.** Pixel systems like Imagen chain 64 to 256 to 1024 diffusion upsamplers, trained on deliberately corrupted low-resolution inputs so they repair artifacts instead of enlarging them. A latent system decodes at 1024px directly.

## Training

### Forward process and objective

With a variance schedule \(\beta_1, \dots, \beta_T\), \(T = 1000\), one noising step is

$$
x_t = \sqrt{1-\beta_t}\, x_{t-1} + \sqrt{\beta_t}\, \epsilon, \qquad \epsilon \sim \mathcal{N}(0, I)
$$

where \(\beta_t\) is the fresh noise variance at step \(t\). Gaussians compose, so any step is reachable in one shot:

$$
x_t = \sqrt{\bar\alpha_t}\, x_0 + \sqrt{1-\bar\alpha_t}\, \epsilon, \qquad \bar\alpha_t = \prod_{s=1}^{t} (1-\beta_s)
$$

\(x_0\) is the clean latent and \(\bar\alpha_t\) the remaining signal variance, sliding from near 1 to near 0. Think of schedules in terms of \(\mathrm{SNR}(t) = \bar\alpha_t / (1-\bar\alpha_t)\). Higher resolutions need schedules shifted toward more noise, because correlated neighboring pixels leak signal. A schedule that never reaches zero SNR at \(t = T\) mismatches sampling, which starts from pure noise, and the model then struggles with very dark or bright images.

The network learns to recover the noise:

$$
\mathcal{L} = \mathbb{E}_{x_0, c, t, \epsilon}\left[\, \big\| \epsilon - \epsilon_\theta(x_t, t, \tau(c)) \big\|_2^2 \,\right]
$$

\(\epsilon_\theta\) is the denoiser, \(\tau(c)\) the text encoding of caption \(c\), and \(t\) is uniform. This MSE is a reweighted variational bound ([DDPM](https://arxiv.org/abs/2006.11239)); the noise target has unit variance at every \(t\), unlike \(x_0\), which is nearly unrecoverable at high noise. Variants: v-prediction (target \(\sqrt{\bar\alpha_t}\epsilon - \sqrt{1-\bar\alpha_t}x_0\)) behaves well at both ends and distills better; min-SNR weighting stops easy low-noise steps dominating; flow matching regresses a velocity along a straight path from data to noise and needs fewer sampling steps.

For classifier-free guidance, replace the caption with the empty string for about 10 percent of examples, so one network learns both conditional and unconditional predictions.

```mermaid
flowchart LR
  accTitle: One diffusion training step
  accDescr: A latent and caption embedding are loaded and the caption is dropped with probability 0.1. A timestep and Gaussian noise are sampled and mixed with the latent by the closed-form forward process. The denoiser predicts the noise, mean squared error against the true noise gives gradients, and the optimizer updates the weights and an exponential moving average copy.
  B[("Shard: latent x0, caption embedding")] --> DROP["Drop caption with p = 0.1"]
  B --> MIX
  T["Sample t uniformly"] --> MIX["Mix: sqrt abar_t x0 + sqrt 1-abar_t eps"]
  N["Sample eps from N of 0, I"] --> MIX
  MIX --> NET["Denoiser: U-Net or DiT"]
  DROP --> NET
  T --> NET
  NET --> LOSS["MSE vs true eps, optional SNR weight"]
  N --> LOSS
  LOSS --> OPT["AdamW, bf16, sharded"]
  OPT --> EMA["EMA weights for eval and serving"]
```

### Stages

1. Autoencoder: reconstruction, perceptual and light adversarial losses; then frozen.
2. Low-resolution pretraining at 256px on the full set, where most concepts are learned at a sixteenth of the 1024px token cost.
3. High-resolution training at 512 then 1024 with aspect buckets on a cleaner subset.
4. Aesthetic fine-tuning on thousands of hand-curated images; Meta's Emu showed this small stage moves human preference a lot.
5. Preference tuning with Diffusion-DPO or reward-weighted fine-tuning on pairwise judgments, fed by logged thumbs and rerolls.
6. Distillation for serving (next section).

### Efficiency

bf16 compute with fp32 master weights. FSDP or ZeRO-3 to shard parameters, gradients and optimizer state: a 3B denoiser with AdamW needs about \(3\text{B} \times 16\) bytes \(= 48\) GB before activations. Activation checkpointing in attention blocks costs about a third more compute and frees memory for larger batches. Keep an EMA of weights (decay near 0.9999) for evaluation and serving; it samples noticeably cleaner.

**Worked example: training compute.** A 2B DiT on 4,096 tokens costs about \(6N\) FLOPs per token for forward plus backward:

$$
6 \times (2 \times 10^{9}) \times 4096 \approx 4.9 \times 10^{13} \ \text{FLOPs per sample}
$$

300M samples at 1024px is \(1.5 \times 10^{22}\) FLOPs. An H100 at 40 percent of about \(10^{15}\) bf16 FLOP/s does \(4 \times 10^{14}\) per second, giving \(3.7 \times 10^{7}\) GPU-seconds: about 10,000 GPU-hours, or five days on 1,024 GPUs before attention overhead. At 256px there are 256 tokens, 16x cheaper per sample, which is why the bulk of samples are seen at low resolution.

### Failure modes

- **Flat loss, improving samples.** Diffusion loss is dominated by the noise level; track FID and alignment on a fixed prompt set instead.
- **Attribute leakage** ("red cube, blue sphere" both red). Denser captions, a stronger text encoder, compositional data.
- **Garbled text.** Character-aware encoders, more latent channels, captions that transcribe visible text.
- **Memorization.** Stricter dedup; compare outputs to training embeddings.
- **Loss spikes.** QK normalization, gradient clipping, lower learning rate, restart from a good checkpoint.

## Inference and sampling

Sampling starts from \(x_T \sim \mathcal{N}(0, I)\) and walks backward. The DDPM step is

$$
x_{t-1} = \frac{1}{\sqrt{1-\beta_t}}\left(x_t - \frac{\beta_t}{\sqrt{1-\bar\alpha_t}}\, \hat\epsilon\right) + \sigma_t z, \qquad z \sim \mathcal{N}(0, I)
$$

with \(\hat\epsilon\) the predicted noise and \(\sigma_t\) the injected randomness. Naively that is 1,000 network calls, and samples under-follow the prompt.

**Classifier-free guidance** runs the denoiser with and without the prompt and extrapolates:

$$
\hat\epsilon = \epsilon_\theta(x_t, t, \varnothing) + w \big(\epsilon_\theta(x_t, t, c) - \epsilon_\theta(x_t, t, \varnothing)\big)
$$

\(w\) is the guidance scale; \(w = 1\) is plain conditional sampling, and 4 to 9 is typical. The difference term points toward "more like the text". Costs: two evaluations per step (batched), lower diversity, and oversaturated, plastic-looking images at high \(w\). A negative prompt replaces \(\varnothing\) with text to steer away from ([Ho and Salimans](https://arxiv.org/abs/2207.12598)).

**Fewer steps.** DDIM treats the trained model as a deterministic sampler that skips timesteps: estimate \(\hat x_0 = (x_t - \sqrt{1-\bar\alpha_t}\,\hat\epsilon)/\sqrt{\bar\alpha_t}\), then jump to \(x_s = \sqrt{\bar\alpha_s}\,\hat x_0 + \sqrt{1-\bar\alpha_s}\,\hat\epsilon\) for an earlier \(s\). Twenty to fifty steps stay close to full quality; higher-order solvers (DPM-Solver++, UniPC) reach it in 15 to 25. Determinism also makes seeds reproducible, which "vary this image" features need. Distillation goes further: progressive distillation halves steps repeatedly, consistency models map any noisy point straight to a clean one, adversarial distillation (SDXL Turbo) adds a discriminator for crisp one-to-four-step output, and guidance distillation folds CFG into a single evaluation.

| Knob or method | Typical | Quality | Latency | Watch for |
|---|---|---|---|---|
| DPM-Solver++ steps | 20 to 30 | Near full | Linear in steps | Smearing below about 12 |
| DDPM ancestral | 250 to 1000 | Most diverse | Far too slow | Offline use only |
| Guidance scale \(w\) | 4 to 9 | Adherence up, diversity down | 2x compute unless distilled | Oversaturation |
| Guidance distillation | 1 call per step | Close to CFG | About 2x faster | Narrow \(w\) range |
| Consistency or adversarial distillation | 1 to 4 steps | Good, less variety | 5 to 20x faster | Long compositional prompts |
| Four seeds per prompt | 4 | Covers interpretations | Batched, about 1.5 to 2x one | Rerolls if all miss |

## Evaluation

### Offline

Use fixed prompt suites that isolate skills: DrawBench and PartiPrompts (counting, color, spatial relations, rare combinations, text rendering), GenEval (detector-checked presence, count, color, position), T2I-CompBench (attribute binding). Use several seeds per prompt.

**FID** compares Inception feature statistics of real and generated images, typically on 30k COCO captions:

$$
\mathrm{FID} = \|\mu_r - \mu_g\|_2^2 + \mathrm{Tr}\!\left(\Sigma_r + \Sigma_g - 2(\Sigma_r \Sigma_g)^{1/2}\right)
$$

\(\mu\) and \(\Sigma\) are feature means and covariances for real (\(r\)) and generated (\(g\)) sets. It covers realism and diversity but ignores the prompt. Inception Score saturates on modern models.

**CLIPScore** rescales cosine similarity between CLIP image embedding \(v\) and prompt embedding \(u\): \(\mathrm{CLIPScore} = 2.5 \cdot \max(\cos(u, v), 0)\). CLIP was trained contrastively over a batch of \(B\) pairs:

$$
\mathcal{L}_{\text{CLIP}} = -\frac{1}{2B}\sum_{i=1}^{B}\left[\log\frac{e^{s_{ii}/\tau}}{\sum_j e^{s_{ij}/\tau}} + \log\frac{e^{s_{ii}/\tau}}{\sum_j e^{s_{ji}/\tau}}\right]
$$

\(s_{ij}\) is the cosine similarity of image \(i\) and text \(j\), and \(\tau\) a learned temperature. Random batches almost never contain near-miss negatives like "dog left of cat" against "cat left of dog", so CLIP learns something close to bag-of-words matching and CLIPScore misses composition errors. VQA-based metrics (TIFA, DSG) help: an LLM turns the prompt into yes/no questions and a VQA model answers them on the image.

**Fairness:** for neutral prompts ("a photo of a nurse"), generate a few hundred images, classify the three attributes, and report total variation distance from a target distribution.

**Human evaluation:** side-by-side preference against the current model on the same prompts (win rate with confidence interval), a 3-level adherence rating per image, and photorealism comparisons against real photos. Use trained raters, several per item, and track agreement. Preference models (PickScore, ImageReward, HPS) approximate this cheaply between releases.

| Metric | Catches | Misses | Cost |
|---|---|---|---|
| FID | Realism and diversity shifts, collapse | Adherence; fine taste | Cheap, 10k+ samples |
| CLIPScore | Wrong or missing main subject | Counts, positions, binding, negation; fooled by drawn text | Cheap |
| VQA-based (TIFA, GenEval) | Specific compositional errors | Aesthetics; VQA model errors | Moderate |
| Preference model | Taste trends | Reward hacking, rater bias | Cheap |
| Human side-by-side | What users notice | Rare failures | Expensive |
| Attribute audit | Demographic skew | Stereotyped context and setting | Moderate |

### Online

Engagement: save or download rate, shares, click-through on results, thumbs. Friction: reroll rate (same prompt, new seed), immediate prompt edits, abandonment while waiting. Business: paid conversion and GPU cost per active user per month. System: per-stage p50 and p95 latency, throughput, GPU utilization, refusal rate by category. Reroll rate deserves its own dashboard because it is a quality signal and a cost multiplier at once.

## Serving system

```mermaid
flowchart TB
  accTitle: End-to-end text-to-image system
  accDescr: Offline, the data pipeline feeds training, an evaluation gate approves or rejects candidates, and an optimization step distills and quantizes approved models. Online, a request passes autocomplete, prompt safety, prompt enhancement, text encoding, batched denoising, latent decoding, image safety, and upscaling with watermarking before delivery. Logs return to the data pipeline.
  subgraph OFF["Offline"]
    DP["Data pipeline"] --> TR["Training cluster"]
    TR --> EG{"Eval gate: metrics, human SxS, fairness"}
    EG -->|pass| OP["Optimize: distill, quantize, compile"]
    EG -->|fail| TR
  end
  subgraph ON["Online"]
    UI["Client with autocomplete"] --> PS{"Prompt safety"}
    PS -->|block| RJ["Refusal message"]
    PS -->|ok| PE["Prompt enhancer LLM"]
    PE --> TE["Text encoder"]
    TE --> DM["Denoiser workers, batched"]
    DM --> DEC["Latent decoder"]
    DEC --> IS{"Image safety"}
    IS -->|unsafe| RJ
    IS -->|safe| SR["Upscale and watermark"]
    SR --> CDN["Object store and CDN"]
  end
  OP --> DM
  CDN --> LOG[("Logs: prompts, outputs, feedback")]
  LOG --> DP
```

- **Autocomplete:** a small LM suggests continuations, steering users toward descriptive prompts.
- **Prompt safety:** a classifier or small LLM judge blocks disallowed requests before any GPU work; it must handle misspellings and euphemisms.
- **Prompt enhancer:** an LLM expands terse prompts into the dense style seen after recaptioning, keeps every user constraint, and can diversify unspecified demographics across the four samples. Show the rewrite.
- **Image safety:** harmless prompts can still produce unsafe pixels; blocks are logged for retraining.
- **Finishing:** upscale, invisible watermark plus C2PA provenance metadata, store, return URLs.

```mermaid
sequenceDiagram
  accTitle: Request sequence for one generation
  accDescr: The client sends a prompt to the gateway, which calls prompt safety and then the enhancer, sends the enhanced prompt with four seeds to a generation worker, has outputs checked by image safety, finalized by the upscaler, and returns URLs to the client while logging asynchronously.
  participant C as Client
  participant G as Gateway
  participant S as Prompt safety
  participant E as Enhancer
  participant W as Generation worker
  participant H as Image safety
  participant U as Upscaler
  participant L as Log store
  C->>G: prompt, settings
  G->>S: classify prompt
  S-->>G: allowed
  G->>E: expand prompt
  E-->>G: enhanced prompt
  G->>W: enhanced prompt, 4 seeds
  W->>W: encode, 25 guided steps, decode
  W->>H: 4 images
  H-->>W: all safe
  W->>U: 4 images
  U-->>G: image URLs
  G-->>C: images and enhanced prompt
  G--)L: prompt, outputs, timings
```

**Worked example: latency budget.** 2B DiT, 4,096 tokens, 25 steps, four images with CFG, so 8 sequences per step. One sequence forward is \(2 \times 2\times10^{9} \times 4096 \approx 1.6\times10^{13}\) FLOPs, about \(2.1\times10^{13}\) with attention. Total: \(8 \times 25 \times 2.1\times10^{13} = 4.2\times10^{15}\) FLOPs, or 8.4 s on one H100 at 50 percent of \(10^{15}\) FLOP/s. Too tight. Guidance distillation halves it to 4.2 s (or split across two GPUs). Budget: prompt safety 50 ms, enhancer 600 ms, text encode 80 ms, denoise 4.2 s, decode 400 ms, image safety 80 ms, upscale and watermark 500 ms, network and queueing 1 s. About 7 s, leaving p95 headroom.

**Worked example: fleet size.** 2M requests/day is \(2\times10^{6}/86{,}400 \approx 23\)/s, about 70/s at a 3x peak. At 4.5 GPU-seconds each, peak needs \(70 \times 4.5 \approx 315\) busy GPUs, or about 450 at 70 percent utilization, plus a few dozen for the enhancer, safety models and upscalers. A 15 percent reroll rate multiplies this by 1.15; moving 30 percent of traffic to a four-step fast tier saves roughly a quarter.

| Technique | Latency | Cost | Quality risk |
|---|---|---|---|
| Better solver, fewer steps | Large drop | Large drop | Low down to about 20 steps |
| Guidance distillation | About 2x | About half | Low |
| Step distillation (LCM, adversarial) | 5 to 20x | Large drop | Medium on complex prompts |
| int8 or fp8 weights | 1.3 to 2x | Lower | Low with calibration; check faces and text |
| Compiled graphs, fused attention | 1.2 to 1.5x | Lower | None |
| Dynamic batching by resolution bucket | Small queue wait | Much higher throughput | None |
| Router: small model for easy prompts | Lower average | Lower | Low if router is accurate |

**Safety and monitoring.** Layers: filtered data, prompt classifier, output classifier, watermark, per-account rate limits, and a human review queue for appeals. Watch refusal rate by category (spikes mean a regression or a new jailbreak), output block rate (generator or enhancer drift), per-stage latency, and attribute distributions on a canary prompt set after each deploy. Ship behind a traffic split and compare save and reroll rates first.

## Follow-ups and extensions

- **Personalization:** DreamBooth or LoRA adapters learned from a few user photos, served as small weight deltas on the shared base (Chapter 10).
- **Editing:** inpainting and outpainting with masked image and mask as extra input channels; instruction editing trained on before-instruction-after triples.
- **Spatial control:** ControlNet, a trainable encoder copy consuming edges, depth or pose.
- **Multilingual:** translate in the enhancer for a quick win, or fine-tune with a multilingual encoder for culture-specific concepts.
- **RLHF:** reward model on preference pairs plus Diffusion-DPO, with a KL tie to the base to resist reward hacking.
- **Video:** add temporal attention to the same latent design (Chapter 11).

## Interview questions

### Clarifying

**Which requirements would you pin down first?**
Resolution and latency together decide between pixel cascades and latent diffusion, and how many steps fit. Prompt length and language decide the text encoder and its context. Data size and caption quality decide whether recaptioning is a first-class component. Safety and fairness scope add models to both the data pipeline and the request path. Traffic and images per request size the fleet.

**Is "10 seconds" p50 or p95, and for how many images?**
I would assume p95 for a batch of four, since that is how results are usually shown. If it meant p50 for one image, a 25-step latent model fits on one GPU easily and step distillation would be unnecessary quality loss. If it meant p95 for four images including queueing, guidance distillation becomes nearly mandatory. It also tells me whether queueing sits inside the budget, which sets how hot I can run GPUs.

**What does "unbiased across age, gender and race" mean operationally?**
For prompts that leave those attributes unspecified, results should vary, and over many generations the distribution should stay within a set distance of an agreed target. Prompts that specify attributes must be followed exactly. The target itself (uniform or a reference population) is a policy choice I would ask the interviewer to own. That gives an audit number, a release threshold, and two places to act: data weighting and prompt diversification.

### Design and trade-offs

**Trade-off: diffusion versus autoregressive.**
Diffusion gives the best detail and a step-count dial that trades speed for quality without retraining. Autoregressive models supervise every token per pass and fit an LLM stack, which suits one model that both chats and draws. Their cost here is thousands of sequential token steps per 1024px image and tokenizer-limited detail. For a dedicated service with a 10 second target, diffusion wins.

**Trade-off: pixel cascade versus latent diffusion.**
A cascade keeps every stage in pixel space, which helps small text and faces, but runs three diffusion models in sequence and the upsamplers are expensive. Latent diffusion runs one denoiser on a 48x smaller tensor, so training and serving are far cheaper, with detail capped by the autoencoder. Sixteen latent channels recover most of that. Under 10 seconds I would choose latent diffusion plus a light upscaler.

**Trade-off: guidance scale.**
Raising \(w\) increases adherence and contrast but reduces seed diversity and eventually oversaturates. Lowering it gives variety and natural color but drifts from the prompt. Sweep \(w\), plot FID against a VQA or CLIP alignment score, and set the default at the knee, usually 5 to 7. A "creativity" slider can expose it to power users.

**Trade-off: U-Net or DiT?**
U-Nets are proven at 1 to 3B parameters and converge faster on small budgets thanks to convolutional priors. DiTs scale more predictably, share kernels and parallelism with LLM infrastructure, and handle aspect ratios as variable token counts. Attention cost grows with the square of tokens, so patch size is the main lever. For a new large build I would pick DiT while noting a U-Net also meets the requirements.

**Trade-off: cache text embeddings or compute online?**
Caching removes an encoder pass from every step, but T5-XXL embeddings are near a megabyte per caption, hundreds of terabytes for 500M. Online encoding costs 10 to 20 percent more step time and lets you change caption mixes freely. A middle path caches for the high-resolution subset that sees many epochs, possibly in fp8. I would decide by comparing the storage bill with the extra GPU-hours, which usually favors online encoding for the big low-resolution pass.

### Deep dives

**Walk through one training step.**
Load latent \(x_0\) and caption embedding, dropping the caption with 10 percent probability. Sample \(t\) uniformly and \(\epsilon\) from a standard normal, and form \(x_t\) in closed form. Run the denoiser on \(x_t\), the timestep embedding and text tokens. Take MSE against \(\epsilon\), optionally SNR-weighted, backpropagate under bf16 and sharding, and update the EMA copy.

**Why predict noise instead of the clean image?**
At high noise the clean image is nearly unrecoverable, so an \(x_0\) target yields blurry averages and badly scaled errors across timesteps. The noise target has unit variance everywhere, balancing the loss and stabilizing optimization, and it relates directly to the score the sampler needs. At very low noise the roles flip, which is why v-prediction blends the two. Either target is a reparameterization of the same information, so the choice is about optimization, not expressiveness.

**Estimate denoising latency for four 1024px images.**
A 2B DiT on 4,096 tokens costs about \(2.1\times10^{13}\) FLOPs per sequence forward including attention. Four images with CFG is 8 sequences per step; 25 steps make \(4.2\times10^{15}\) FLOPs. At 50 percent of an H100's \(10^{15}\) FLOP/s that is 8.4 s. Guidance distillation or a second GPU brings it to about 4 s, within budget.

**Estimate the GPU fleet for 2M requests a day.**
About 23 requests per second on average, 70 at a 3x peak. At 4.5 GPU-seconds each, that is 315 busy GPUs, about 450 at 70 percent utilization, plus a few dozen for the enhancer, safety and upscalers, times the reroll factor. At 2 to 3 dollars per GPU-hour, provisioning for peak all day costs roughly 22,000 to 32,000 dollars a day. Steps per image and the fast-tier share are the biggest levers.

### Operations and failure modes

**A new model has better FID but users reroll more. Why?**
FID rewards realism on COCO-style prompts and says nothing about adherence on long user prompts. The model likely got prettier but less faithful, perhaps from an aesthetic stage pulling toward a house style. Compare VQA-based adherence and run a side-by-side on real logged prompts. Then rebalance or weaken the aesthetic stage, and add real-prompt adherence to the release gate.

**Users bypass the prompt classifier. What now?**
Add the discovered patterns to its training data, raise sensitivity in the affected category, and lean on the output classifier, which ignores phrasing. Red-team regularly with generated adversarial prompts and route borderline cases to an LLM judge. Per-account rate limits slow down systematic probing. Track false positives as you tighten, since over-blocking art and medical content hurts users.

**People in outputs skew after a release. What do you do?**
Confirm with the canary audit against the previous model and the target. Check likely causes: a skewed fine-tuning set, an aesthetic filter correlated with an attribute, or an enhancer change. Mitigate quickly by diversifying unspecified attributes in the enhancer. Then fix the data weighting and make the audit a blocking release check.

**p95 latency doubled while GPU utilization is low. Where do you look?**
Low utilization with high latency points away from the denoiser, toward queueing or other stages. Check per-stage timings for the enhancer LLM, safety services and storage uploads, and check whether the batcher waits too long to fill batches at low traffic. Mixed resolution buckets fragmenting batches is another usual cause. Per-stage timeouts, a capped batching wait and per-bucket queues fix most of it.

## A 45-minute walkthrough

| Minutes | Cover | Draw |
|---|---|---|
| 0 to 5 | Resolution, latency percentile, prompt length, languages, data and captions, safety and fairness scope, traffic | Requirements with numbers |
| 5 to 9 | \(p(x \mid c)\); diffusion versus autoregressive versus GAN; pick latent diffusion and name the cost | Small comparison table |
| 9 to 16 | Filters, dedup, recaptioning, fairness weights, caching with storage estimate | Data pipeline |
| 16 to 23 | Text encoder, autoencoder, U-Net or DiT, cross-attention, timestep conditioning | Denoiser diagram |
| 23 to 29 | Forward process, noise loss, caption dropout, resolution stages, bf16 and FSDP, compute estimate | Training step and two equations |
| 29 to 33 | CFG, solvers, distillation, knob trade-offs | Guidance equation |
| 33 to 37 | FID, CLIPScore and its blind spots, VQA metrics, human side-by-side, fairness audit, reroll rate | Metric list with gaps |
| 37 to 43 | Request path with both safety checks and enhancer, latency budget, fleet size, optimizations | End-to-end architecture |
| 43 to 45 | Personalization, editing, ControlNet, RLHF; the biggest risk | Point at the diagram |
