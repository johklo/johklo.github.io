---
title: "MLOps & LLMOps"
description: "MLOps and LLMOps, split into tool basics, labs and operational design for the fictional Bookway service"
date: 2026-10-25T19:30:00+09:00
weight: 3
tags: ["mlops", "llmops", "platform-engineering"]
sidebar:
  open: false
---

This section splits into tool basics, labs and operational design. It connects MLOps (model training and serving) with LLMOps (retrieval, generation and tool calls). The guides are written in Korean.

| Subsection | What it covers | Good place to start |
| --- | --- | --- |
| [MLOps](mlops/) | Operational design and tool roles for the Bookway bookstore recommender | [MLOps overview](mlops/) |
| [MLOps > Tool basics](mlops/basics/) | MLflow, Feast, Kubeflow Pipelines and BentoML from install to intermediate use | [MLflow basics](mlops/basics/mlflow/) |
| [MLOps > Labs](mlops/labs/) | MLflow and Azure ML 01-06, ML platform labs 00-10 | [Lab index](mlops/labs/) |
| [LLMOps](llmops/) | RAG, evaluation, observability, guardrails and release for the Bookway help assistant | [LLMOps overview](llmops/) |

```mermaid
flowchart TD
    accTitle: MLOps & LLMOps section map
    accDescr: MLOps and LLMOps sit under the parent section. MLOps holds tool basics, labs and the Bookway design guide; LLMOps holds the Bookway help assistant guide.
    R["MLOps & LLMOps"] --> M["MLOps"]
    R --> L["LLMOps"]
    M --> MB["Tool basics<br/>MLflow, Feast, KFP, BentoML"]
    M --> ML["Labs<br/>MLflow and Azure ML, ML platform integration"]
    M --> MD["Bookway recommender design<br/>from data versions to monitoring"]
    L --> LD["Bookway help assistant guide<br/>retrieval, evaluation, observability, guardrails, release"]
```

Read in order: tool basics, labs, then design by requirement. The related book notes are [Machine Learning Platform Engineering](/docs/tech/machine-learning-platform-engineering/) and [AI Agents and Applications](/docs/tech/ai-agents-and-applications/).

{{< section-list >}}
