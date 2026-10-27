---
title: "OpenTelemetry: API, 검색, 모델, 도구의 공통 관측"
description: "Bookway 요청의 인과관계를 서비스 경계를 넘어 연결하고 수집 정책을 통제"
date: 2026-10-25T08:43:00+09:00
weight: 120
tags: ["llmops", "opentelemetry", "observability"]
aliases:
  - "/docs/tech/llmops/opentelemetry/"
---

OpenTelemetry는 trace, metric, log를 생성, 전달하는 공통 API, SDK, 규약을 제공한다. 저장소나 대시보드 자체가 아니라, 승인된 backend에 연결하는 계측 기반이다.

## Bookway의 관측 경계

```text
브라우저 → API request span
             ├─ retrieval / policy-v3
             ├─ gateway / actual model
             ├─ order tool / status
             └─ output validation
  → OTel Collector: 필터, batch, 전송
  → 승인된 trace backend / Langfuse / Application Insights 등
```

HTTP, 큐, 비동기 경계를 넘어 trace context를 전달한다. trace ID는 관측용이며 고객 인증 token이나 거래 멱등 키가 아니다. 외부에서 들어온 baggage를 그대로 권한 판단이나 로그 attribute로 신뢰하지 않는다.

## 외부 전송 없는 로컬 계측

`opentelemetry-api`, `opentelemetry-sdk` 환경에서 Console exporter로 작은 span 구조를 확인한다.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor, ConsoleSpanExporter,
)

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("bookway.assistant")

with tracer.start_as_current_span("bookway.policy-request") as root:
    root.set_attribute("bookway.release_id", "help-r8")
    with tracer.start_as_current_span("retrieve") as child:
        child.set_attribute("bookway.policy_version", "policy-v3")
        child.set_attribute("bookway.source_count", 1)
provider.shutdown()
```

합성 span이며 검색이나 모델이 실제 실행된 기록은 아니다. 앱에 붙일 때는 span이 실제 작업 시작, 종료, 오류를 감싸게 한다. 운영에서는 BatchSpanProcessor와 OTLP exporter, Collector를 검토한다.

## 수집 정책과 지연 해석

prompt, 응답, 문서 원문은 기본 attribute로 넣지 않는다. release, 모델, token 수, duration, 오류 유형을 우선 남기고 원문이 필요하면 동의, 마스킹, 권한, retention을 정한다. GenAI semantic convention은 버전과 안정성 상태를 확인하며, 위 `bookway.*`는 앱의 custom attribute이다.

전체 응답 시간과 TTFT는 별도 측정한다. 하위 span이 병렬이면 duration을 단순히 더한 값이 사용자 대기 시간이 아니다. retry span과 실제 시도 횟수를 남겨 gateway 재시도 비용도 구분한다.

## 운영 장애

export 실패, queue overflow, sampling 누락률을 계측한다. sampling된 trace만으로 전체 청구 금액을 계산하면 빠진 요청이 있다. 비용, 감사에서 완전성이 필요한 기록은 별도 수집 계약을 둔다.

Collector가 민감정보를 걸러도 이미 SDK에서 외부 exporter로 전송했다면 늦다. 원문 제거를 앱에서 먼저 적용하고 수집 경로를 제한한다. 관측 장애가 앱을 멈출지 여부도 업무 위험에 따라 정하되 조용히 성공한 것으로 보고하지 않는다.

[공식 Python 계측](https://opentelemetry.io/docs/languages/python/instrumentation/) / [메트릭, 알림 기반](/docs/tech/ops/mlops/monitoring/) / [Langfuse trace](/docs/tech/ops/llmops/langfuse/)
