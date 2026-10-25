---
title: "vLLM: 자체 모델의 추론 서버 운영"
description: "Bookway의 가중치, chat template, GPU 메모리, 동시성과 생성 API 관리"
date: 2026-10-25T08:43:00+09:00
weight: 90
tags: ["llmops", "vllm", "inference"]
aliases:
  - "/docs/tech/llmops/vllm/"
---

게이트웨이가 전화 교환기라면 vLLM은 실제 답변을 계산하는 엔진입니다. 모델 가중치를 로딩하고 요청 배치, 메모리 사용을 관리하며 생성 API를 제공합니다. Bookway가 관리형 모델만 쓰면 반드시 운영할 필요는 없습니다.

## 자체 추론을 선택하는 조건

데이터 경계, 지속 부하, 모델 제어가 이점일 수 있지만 GPU 비용, 패치, 용량, 장애 대응을 직접 맡습니다. 드문 요청이면 상시 GPU보다 관리형 API가 합리적일 수 있습니다. API 단가만 비교하지 않고 유휴 시간과 운영 인력을 포함합니다.

기본 개발 경로는 지원되는 Linux GPU 환경입니다. Windows 작업 PC에서는 지원 조합의 Linux 호스트나 컨테이너 환경을 사용하고 GPU driver, CUDA, vLLM 호환성을 확인합니다.

## 모델 고정과 서버 시작

아래는 다운로드, license 확인을 마친 chat 모델을 `BOOKWAY_MODEL_PATH`로 지정하고, vLLM이 설치된 지원 환경에서 실행하는 명령입니다. 필요한 GPU 메모리는 모델, dtype, 문맥, 동시성에 따라 달라집니다.

```bash
vllm serve "$BOOKWAY_MODEL_PATH" --served-model-name bookway-chat --host 127.0.0.1 --port 8000 --max-model-len 4096
```

위 명령은 Linux 셸 기준입니다. 운영 API는 TLS, 인증 proxy, 네트워크 통제를 추가하고 직접 외부 공개하지 않습니다.

| 고정할 값 | 이유 |
| --- | --- |
| 가중치 revision, 지문 | 같은 모델 이름의 변경 방지 |
| tokenizer, chat template | 메시지 역할, 도구 형식 |
| dtype, 양자화 설정 | 메모리와 품질 영향 |
| 문맥 길이, 동시성, batch | 메모리, 큐, 지연 |
| vLLM, driver, GPU | 성능과 호환성 재현 |

## OpenAI-compatible의 범위

SDK의 endpoint 형태가 같아도 모든 provider 기능이 같지는 않습니다. chat template가 없는 모델은 chat 요청을 바로 처리하지 못할 수 있고, tool calling parser, structured output은 모델과 서버 설정을 맞춰야 합니다.

Bookway의 프롬프트, 도구 스키마, 거절 사례를 실제 모델로 평가한 뒤 [LiteLLM](/docs/tech/ops/llmops/litellm/) alias에 연결합니다. 임베딩, rerank endpoint도 지원 모델과 API가 별도이므로 생성 모델 한 서버가 모든 역할을 한다고 가정하지 않습니다.

## 용량과 장애 대응

KV cache는 추론 중 토큰 상태를 재사용하는 내부 메모리이며 [Redis의 완성 답변 캐시](/docs/tech/ops/llmops/redis/)와 다릅니다. 긴 context와 많은 동시 요청이 GPU 메모리를 압박합니다. TTFT, 출력 token/s, 큐 대기, 실패, GPU 메모리를 함께 봅니다.

OOM에서 무제한 재시도하지 않고 문맥, 동시성, 모델 크기를 조정합니다. 준비되지 않은 서버는 트래픽에서 제외하고, 배포 전 가중치 다운로드, warm-up, 지원 요청 형태를 확인합니다. 새 모델을 검증하기 전 운영 alias를 바꾸지 않습니다.

[공식 online serving](https://docs.vllm.ai/en/stable/serving/online_serving/) / [공통 실행 기반](/docs/tech/ops/mlops/runtime/) / [배포, 복구 계약](/docs/tech/ops/llmops/release/)
