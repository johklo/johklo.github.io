---
title: "Token Factory: A Reference Architecture for LLM Inference at Scale"
description: "The layers, technology stack, request flow, and control loops of a platform that turns GPUs into tokens, the NVIDIA DGX SuperPOD blueprint, and how to build the equivalent on Azure"
date: 2026-11-26T08:00:00+09:00
tags: ["llm-inference", "gpu", "kubernetes", "vllm", "dynamo", "architecture"]
math: false
draft: false
---

A **token factory** is an inference platform whose product is generated tokens. Raw inputs are power, GPUs, and model weights. The output is a stream of tokens sold or consumed at a target latency and cost. The term describes a shift in how inference platforms are designed: instead of "hosting a model", the goal is to maximize **useful tokens per second per dollar** while meeting latency targets for every tenant.

This post describes a vendor-neutral reference architecture, the role of each layer, the open source and commercial components that commonly fill each role, and the design decisions that matter most.

## 1. What the factory optimizes

Every design choice trades off three numbers.

| Metric | Definition | Why it matters |
| --- | --- | --- |
| **TTFT** (time to first token) | Time from request arrival to the first output token | Perceived responsiveness. Dominated by queueing and prefill |
| **ITL / TPOT** (inter-token latency, time per output token) | Average gap between output tokens | Reading speed for chat, total time for long outputs. Dominated by decode |
| **Throughput** | Output tokens per second per GPU (or per node) | Directly sets cost per million tokens |
| **Goodput** | Throughput that still meets the TTFT and ITL targets | The number that actually matters. Raw throughput at broken latency is waste |
| **Cost per 1M tokens** | (GPU hour cost + overhead) / tokens produced per hour | The business metric |

The two phases of generation behave very differently, and most of the architecture follows from this.

| Phase | Work | Bottleneck |
| --- | --- | --- |
| **Prefill** | Process the whole prompt in parallel and build the KV cache | Compute bound. Long prompts take long |
| **Decode** | Generate one token at a time, reading the full KV cache each step | Memory bandwidth bound. Scales with concurrency and context length |

The **KV cache** (attention keys and values for every token in flight) is the central resource of the factory. It decides how many requests fit on a GPU, whether a repeated prompt prefix can be reused, and how much data must move when work is split across GPUs.

## 2. Reference architecture

```mermaid
flowchart TB
    accTitle: Token factory layered architecture
    accDescr: Clients call an API gateway that handles authentication, quotas, and metering. An inference-aware router picks a model pool and a specific replica based on load and KV cache state. Model serving engines run on GPU nodes connected by NVLink and RDMA. A control plane handles scheduling, autoscaling, and model lifecycle. Storage serves model weights and offloaded KV cache. Observability collects metrics from every layer.
    C["Clients<br/>apps, agents, batch jobs"] --> GW

    subgraph EDGE["Access layer"]
        GW["API gateway<br/>authn, tenant quotas, token rate limits, metering"]
    end

    subgraph ROUTE["Routing layer"]
        R["Inference-aware router<br/>model selection, KV/prefix-aware load balancing, admission control"]
    end

    subgraph SERVE["Serving layer"]
        P1["Prefill pool"]
        D1["Decode pool"]
        A1["Aggregated pool<br/>(prefill + decode on same GPU)"]
    end

    subgraph INFRA["GPU infrastructure"]
        G["GPU nodes<br/>HBM, NVLink / NVSwitch"]
        N["Scale-out fabric<br/>InfiniBand or RoCE (RDMA)"]
    end

    subgraph CTRL["Control plane"]
        K["Kubernetes + GPU operator"]
        S["Gang / topology-aware scheduler"]
        AS["Autoscaler / planner<br/>prefill:decode ratio, replicas"]
        MR["Model registry and rollout"]
    end

    subgraph DATA["Data layer"]
        W["Model weight store<br/>object storage + node-local NVMe cache"]
        KV["KV cache tiers<br/>GPU HBM, CPU DRAM, local SSD, remote"]
    end

    subgraph OBS["Observability"]
        O["Metrics, traces, token accounting<br/>TTFT, ITL, goodput, GPU telemetry"]
    end

    GW --> R
    R --> P1
    R --> A1
    P1 -- "KV transfer" --> D1
    D1 --> GW
    A1 --> GW
    SERVE --> G
    P1 -.-> N
    D1 -.-> N
    CTRL -.-> SERVE
    W -.-> SERVE
    KV <-.-> SERVE
    SERVE -.-> O
    ROUTE -.-> O
    EDGE -.-> O
```

### Layer roles and common technology

| Layer | Role | Typical components |
| --- | --- | --- |
| Access | Single API surface (often OpenAI compatible), authentication, per-tenant quotas, **token-based** rate limits, usage metering for billing | Envoy-based gateways, Envoy AI Gateway, LiteLLM, Kong, cloud API management |
| Routing | Pick the model pool and the replica. Use queue depth, KV cache utilization, and prefix overlap instead of round robin. Shed or queue load when the fleet is saturated | Gateway API Inference Extension (InferencePool, endpoint picker), llm-d inference scheduler, NVIDIA Dynamo router, SGLang router |
| Serving engine | Continuous batching, paged KV cache, prefix caching, quantized kernels, speculative decoding, tensor/pipeline/expert parallelism | vLLM, SGLang, TensorRT-LLM, NVIDIA Triton, Hugging Face TGI |
| Distributed serving | Disaggregate prefill and decode, move KV cache between GPUs, manage KV across memory tiers | NVIDIA Dynamo (NIXL, KVBM, Planner), llm-d, LMCache, Mooncake |
| Infrastructure | GPUs with large HBM, NVLink within a node or rack, RDMA fabric between nodes | NVIDIA H100/H200/B200/GB200, AMD MI300 series, InfiniBand, RoCE |
| Control plane | Place multi-GPU workloads as a unit, respect topology, scale pools, roll out models | Kubernetes, NVIDIA GPU Operator, Kueue, Volcano, KEDA, Grove, KServe, KAITO |
| Data | Load tens to hundreds of GB of weights fast, keep hot weights local, extend KV cache beyond HBM | Object storage, parallel file systems (Lustre), node-local NVMe, model streaming loaders |
| Observability | Per-request latency, per-tenant token counts, GPU health | Prometheus, OpenTelemetry, NVIDIA DCGM exporter, Grafana |

## 3. Request flow

The flow below shows a disaggregated deployment, where prefill and decode run on separate GPU pools. This matches the design documented for NVIDIA Dynamo and is similar to llm-d.

```mermaid
sequenceDiagram
    accTitle: Request flow through a disaggregated token factory
    accDescr: The client sends a request to the gateway, which authenticates, checks the token quota, and forwards it. The router picks a prefill worker using KV cache overlap and load. The prefill worker computes the KV cache and the decode worker pulls it over NVLink or RDMA. The decode worker streams tokens back through the gateway, which counts tokens for billing. KV events update the router's view of cached prefixes.
    participant Cl as Client
    participant GW as API gateway
    participant RT as Router
    participant PF as Prefill worker
    participant DC as Decode worker
    participant OB as Metering
    Cl->>GW: POST /v1/chat/completions (stream)
    GW->>GW: Authenticate, check tenant token quota
    GW->>RT: Forward with tenant and priority
    RT->>RT: Score workers by prefix overlap, queue, KV usage
    RT->>PF: Prefill (reuse cached prefix blocks if any)
    PF-->>RT: KV ready + transfer metadata
    RT->>DC: Decode on selected worker
    DC->>PF: Pull KV cache (NVLink in node, RDMA across nodes)
    loop each output token
        DC-->>GW: Token chunk (SSE)
        GW-->>Cl: Token chunk
    end
    GW->>OB: Input tokens, output tokens, TTFT, ITL
    PF-->>RT: KV events (blocks stored or evicted)
```

In an **aggregated** deployment, one worker does both phases. It is simpler and is the right default for small models, short prompts, or low traffic. Disaggregation pays off when prompts are long, traffic is high, and the two phases need different scaling and parallelism.

## 4. Disaggregated prefill and decode

```mermaid
flowchart LR
    accTitle: Aggregated versus disaggregated serving
    accDescr: In aggregated serving, each GPU worker runs prefill and decode, so long prompts stall token generation for other requests. In disaggregated serving, a prefill pool builds KV cache and transfers it to a decode pool, and a planner scales each pool independently.
    subgraph AGG["Aggregated"]
        direction TB
        W1["Worker GPU<br/>prefill + decode interleaved"]
    end
    subgraph DIS["Disaggregated"]
        direction TB
        PP["Prefill pool<br/>compute-heavy, larger TP"] -- "KV cache over NVLink / RDMA" --> DP["Decode pool<br/>bandwidth-heavy, many concurrent sequences"]
        PL["Planner"] -. "scale prefill" .-> PP
        PL -. "scale decode" .-> DP
    end
```

| Aspect | Aggregated | Disaggregated |
| --- | --- | --- |
| Interference | A long prefill pauses decode for every request in the batch, causing ITL spikes | Decode runs without prefill interruptions |
| Scaling | One replica count | Prefill and decode scale separately as the input/output length mix changes |
| Parallelism | One setting for both phases | Different tensor parallelism per phase |
| Cost | No KV transfer | KV transfer needs fast interconnect. Over plain TCP across nodes, transfer can dominate TTFT |
| Operational complexity | Low | Higher: two pools, transfer layer, planner |

## 5. KV cache management

Because KV cache decides both capacity and latency, mature factories treat it as a managed, tiered resource.

```mermaid
flowchart LR
    accTitle: KV cache tiers
    accDescr: KV blocks live in GPU HBM. Under memory pressure or for reuse they are offloaded to CPU DRAM, then local SSD, then remote shared storage. Blocks are recalled to HBM when a request with the same prefix arrives, and the router prefers workers that already hold the prefix.
    H["GPU HBM<br/>fastest, smallest"] <--> C["CPU DRAM"]
    C <--> S["Local NVMe SSD"]
    S <--> R["Remote / shared store"]
    RT["Router"] -. "prefers workers that hold the prefix" .-> H
```

- **Paged attention** stores KV in fixed-size blocks so memory is not wasted on padding.
- **Prefix caching** reuses blocks for identical prompt prefixes (system prompts, few-shot examples, RAG context, multi-turn chat history). A high prefix hit rate lowers TTFT and prefill compute.
- **Prefix-aware routing** sends a request to the worker that already holds its prefix. Random load balancing destroys cache reuse.
- **Offloading** moves cold blocks to cheaper tiers instead of dropping them, so long multi-turn sessions do not recompute the prompt.

## 6. Control loops

A token factory is driven by feedback loops more than static configuration.

```mermaid
flowchart TB
    accTitle: Token factory control loops
    accDescr: Telemetry from the router and engines feeds three loops. The admission loop queues or sheds requests when latency targets are at risk. The scaling loop adjusts replicas and the prefill to decode ratio. The placement loop schedules multi-GPU replicas on nodes with the right topology and pre-warmed weights.
    T["Telemetry<br/>queue depth, KV usage, TTFT, ITL, tokens/s"] --> A["Admission loop<br/>queue, prioritize, shed"]
    T --> SC["Scaling loop<br/>replicas, prefill:decode ratio"]
    T --> PL["Placement loop<br/>gang scheduling, topology, warm weights"]
    A --> RT["Router"]
    SC --> K8S["Kubernetes / planner"]
    PL --> K8S
    K8S --> W["Engines on GPU nodes"]
    W --> T
    RT --> W
```

- **Admission:** when TTFT targets are about to be missed, queue low-priority traffic or reject it early rather than letting every request get slow. Priority classes (interactive versus batch) are common.
- **Scaling:** scale on inference signals (queue length, KV utilization, TTFT), not CPU or raw GPU utilization. GPU utilization from basic telemetry only says a kernel was running, not how much useful work was done.
- **Placement:** a multi-GPU replica must start all of its pods together (gang scheduling) on GPUs connected by NVLink. Partial placement wastes GPUs.
- **Cold start:** loading weights is often the slowest part of scaling. Node-local caches, streaming loaders, and keeping a warm pool decide how fast the factory can absorb a burst.

## 7. Metering and multi-tenancy

Tokens are the unit of cost, so the platform meters tokens, not requests.

| Concern | Approach |
| --- | --- |
| Quotas | Tokens per minute and tokens per day per tenant, enforced at the gateway. Input and output tokens counted separately because their cost differs |
| Fairness | Per-tenant queues or weighted fair scheduling in the router so one tenant's long prompts cannot starve others |
| Isolation | Separate pools for regulated tenants or fine-tuned models. LoRA adapters let many tenants share one base model pool |
| Billing | Token counts from the serving engine (the source of truth), emitted per request with tenant, model, and latency |

## 8. What matters most

1. **Design for goodput, not peak throughput.** Pick TTFT and ITL targets per workload first, then tune batch size and concurrency to the highest throughput that still meets them.
2. **Treat KV cache as the primary resource.** Prefix-aware routing, prefix caching, and tiered offload usually return more than adding GPUs.
3. **Match the interconnect to the topology.** Disaggregation and multi-node parallelism need NVLink within a node or rack and RDMA between nodes. Without RDMA, keep KV transfer inside a node.
4. **Use inference-aware routing.** Round robin load balancing ignores queue depth and cache state and is a common cause of tail latency.
5. **Start aggregated, disaggregate when the data says so.** Long prompts, high concurrency, and ITL spikes from prefill interference are the signals.
6. **Reduce cost per token in the engine.** FP8 or FP4 quantization, speculative decoding, and right-sized tensor parallelism are the largest levers after utilization.
7. **Make scaling fast.** Weight loading and gang scheduling decide how quickly capacity follows demand.
8. **Measure per request.** TTFT, ITL, token counts, and cache hits per request and per tenant. Averages hide the tail that users notice.

## 9. The hardware blueprint: NVIDIA DGX SuperPOD

The architecture above assumes GPU nodes with fast scale-up and scale-out links. NVIDIA's **DGX SuperPOD** is the reference design for building that floor of the factory on premises. The current generation is built from DGX GB200 NVL72 racks.

```mermaid
flowchart TB
    accTitle: DGX SuperPOD GB200 topology
    accDescr: A scalable unit has eight DGX GB200 NVL72 racks. Each rack has 18 compute trays and 9 NVLink switch trays forming one 72-GPU NVLink domain. Racks connect through an InfiniBand compute fabric for GPU-to-GPU traffic across racks, an Ethernet fabric for storage and in-band management, and a separate out-of-band management network. Mission Control and workload managers run on management nodes.
    subgraph SU["Scalable unit (SU) = 8 racks, 576 GPUs"]
        direction LR
        subgraph R1["DGX GB200 NVL72 rack"]
            CT["18 compute trays<br/>each: 2 Grace CPUs + 4 Blackwell GPUs"]
            NS["9 NVLink switch trays<br/>72-GPU NVLink domain, 1.8 TB/s per GPU"]
            CT <--> NS
        end
        R2["Rack 2 ... Rack 8"]
    end
    IB["Compute fabric<br/>InfiniBand NDR 400 Gb/s (4x ConnectX-7 per tray)"]
    ETH["Storage + in-band management fabric<br/>Ethernet via BlueField-3 (2x 200 Gb/s per tray)"]
    OOB["Out-of-band management network"]
    ST["High-performance storage<br/>certified parallel file systems"]
    MG["Management nodes<br/>Mission Control, Run:ai, Base Command Manager, Slurm / Kubernetes"]
    R1 --- IB
    R2 --- IB
    R1 --- ETH
    R2 --- ETH
    ETH --- ST
    MG --- ETH
    MG -.- OOB
    OOB -.- R1
```

| Element | What it is | Why it matters for a token factory |
| --- | --- | --- |
| Scalable unit (SU) | 8 DGX GB200 NVL72 racks (576 GPUs), about 1.2 MW per SU. SuperPOD scales to 128 racks and 9,216 GPUs | The unit of capacity planning, power, cooling, and cabling |
| NVL72 rack | 18 compute trays (2 GB200 Superchips each, so 4 Blackwell GPUs per tray) and 9 NVLink switch trays. All 72 GPUs share one NVLink domain at 1.8 TB/s per GPU | Large models and wide tensor or expert parallelism fit inside one rack. Prefill-to-decode KV transfer can stay on NVLink |
| Compute fabric | InfiniBand NDR 400 Gb/s, four ConnectX-7 NICs per tray | Cross-rack collectives, multi-rack model parallelism, cross-rack KV transfer over RDMA |
| Storage and in-band fabric | Ethernet through BlueField-3 DPUs | Weight loading, checkpoints, datasets, without interfering with GPU traffic |
| Out-of-band network | BMC and switch management | Hardware lifecycle, power, health |
| Software | NVIDIA Mission Control (including Run:ai orchestration), Base Command Manager, Slurm or Kubernetes, NVIDIA AI Enterprise software such as NIM and Dynamo | Cluster provisioning, health, scheduling, and the serving stack from sections 2 to 6 |

The design principle is **separation of traffic by purpose**: NVLink for scale-up inside a rack, InfiniBand for GPU traffic between racks, Ethernet for storage and management. A token factory depends on the first two for parallelism and KV transfer, and on the third for fast weight loading.

## 10. Building the same thing on Azure

On Azure, the hardware layer is delivered as virtual machines on the same class of systems, and the customer builds the control plane, serving stack, and gateway on top.

```mermaid
flowchart TB
    accTitle: Token factory on Azure
    accDescr: Clients call Azure API Management as the AI gateway. Requests go to an AKS cluster where an inference-aware gateway routes to vLLM, SGLang, or Dynamo workers running on ND GB200 v6 or ND H100 v5 node pools connected by InfiniBand. Model weights come from Azure Blob Storage through Azure Managed Lustre and local NVMe. Azure Monitor managed Prometheus and Managed Grafana collect metrics including DCGM GPU telemetry. Training and batch jobs can run on Slurm through CycleCloud Workspace for Slurm on the same VM families.
    C["Clients"] --> APIM["Azure API Management<br/>AI gateway: token limits, metrics, auth"]
    APIM --> AKS
    subgraph AKS["Azure Kubernetes Service"]
        GW["Inference gateway<br/>Gateway API Inference Extension / llm-d / Dynamo router"]
        subgraph GPU["GPU node pools"]
            NP1["ND GB200 v6<br/>4 GPUs per VM, 18 VMs = one NVL72 domain"]
            NP2["ND H100 v5 / ND H200 v5<br/>8 GPUs per VM"]
        end
        OPS["NVIDIA GPU Operator + Network Operator (InfiniBand)<br/>KAITO, KEDA, Kueue"]
        GW --> GPU
        OPS -.-> GPU
    end
    IB["Azure InfiniBand backend network<br/>4x 400 Gb/s per ND GB200 v6 VM"]
    GPU --- IB
    BLOB["Azure Blob Storage<br/>model registry, artifacts"] --> LUS["Azure Managed Lustre<br/>high-throughput weight loading, checkpoints"]
    LUS --> GPU
    NVME["Local NVMe (16 TiB per ND GB200 v6 VM)<br/>weight cache, KV offload"] --- GPU
    GPU -.-> MON["Azure Monitor managed Prometheus<br/>Managed Grafana, DCGM exporter"]
    SL["CycleCloud Workspace for Slurm<br/>training and batch on the same VM families"] -.-> IB
```

| SuperPOD element | Azure equivalent |
| --- | --- |
| DGX GB200 NVL72 rack | 18 ND GB200 v6 VMs. Each VM maps to one compute tray: 2 Grace CPUs, 4 Blackwell GPUs (192 GiB each), 900 GiB memory, 16 TiB local NVMe. The 72 GPUs share one NVLink domain |
| H100-generation DGX nodes | ND H100 v5 and ND H200 v5 VMs with 8 GPUs each |
| InfiniBand compute fabric | Azure InfiniBand backend network: 4x 400 Gb/s Quantum-2 ConnectX-7 per ND GB200 v6 VM, used by NCCL and RDMA KV transfer |
| Storage fabric and certified storage | Azure Managed Lustre for throughput, Azure Blob Storage for durable artifacts, local NVMe for caching |
| Mission Control, Base Command Manager | AKS with GPU node pools for serving, or CycleCloud Workspace for Slurm for training and batch. Azure operates the hardware, power, cooling, and out-of-band management |
| Run:ai style scheduling | Kueue or Volcano on AKS for quotas, priorities, and gang scheduling |
| NVIDIA AI Enterprise serving | vLLM, SGLang, TensorRT-LLM, or Dynamo on AKS, or NVIDIA NIM containers. KAITO automates model deployment on AKS |
| Monitoring | Azure Monitor managed Prometheus, Managed Grafana, NVIDIA DCGM exporter |
| API front door | Azure API Management AI gateway policies for token limits, token metrics, and load balancing across backends |

Points to plan for on Azure:

- **Capacity and quota first.** Large GPU VM families are allocated by region and quota. Reserve capacity for the base load and plan burst capacity separately.
- **Keep NVLink-domain work inside one domain.** For ND GB200 v6, place a model replica that needs wide parallelism within the 18 VMs of one NVL72 domain. Use InfiniBand for traffic between domains.
- **Enable RDMA in Kubernetes deliberately.** Disaggregated serving and multi-node parallelism need the InfiniBand devices exposed to pods, for example through the NVIDIA Network Operator. Without it, KV transfer falls back to TCP.
- **Stage weights close to the GPUs.** Blob to Managed Lustre to local NVMe is the usual path. Cold-start time is usually bounded by this pipeline, not by the engine.
- **Split responsibilities.** Azure runs the physical layer that a SuperPOD owner would run. The customer still owns the serving stack, routing, autoscaling, and metering described in sections 2 to 8.

## References

- [NVIDIA Dynamo: Overall architecture](https://docs.nvidia.com/dynamo/v1.0.0/design-docs/overall-architecture)
- [NVIDIA Dynamo: Disaggregated serving](https://docs.nvidia.com/dynamo/kubernetes/disaggregated-serving/overview)
- [vLLM documentation](https://docs.vllm.ai/)
- [llm-d](https://llm-d.ai/)
- [Gateway API Inference Extension](https://gateway-api-inference-extension.sigs.k8s.io/)
- [NVIDIA DGX SuperPOD reference architecture (DGX GB200)](https://docs.nvidia.com/dgx-superpod/reference-architecture-scalable-infrastructure-gb200/latest/dgx-superpod-components.html)
- [Azure ND GB200 v6 series](https://learn.microsoft.com/azure/virtual-machines/sizes/gpu-accelerated/nd-gb200-v6-series)
- [Azure Managed Lustre](https://learn.microsoft.com/azure/azure-managed-lustre/)
- [CycleCloud Workspace for Slurm](https://learn.microsoft.com/azure/cyclecloud/overview-ccws)
- [SGLang](https://docs.sglang.ai/)
- [Efficient Memory Management for Large Language Model Serving with PagedAttention (Kwon et al., 2023)](https://arxiv.org/abs/2309.06180)
- [DistServe: Disaggregating Prefill and Decoding for Goodput-optimized LLM Serving (Zhong et al., 2024)](https://arxiv.org/abs/2401.09670)
