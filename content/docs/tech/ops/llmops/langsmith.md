---
title: "LangSmith: 실행 트리에서 데이터셋과 실험으로"
description: "Bookway의 재작성, 검색, 도구 흐름을 진단하고 후보별 회귀를 비교"
date: 2026-10-25T08:43:00+09:00
weight: 55
tags: ["llmops", "langsmith", "evaluation", "tracing"]
aliases:
  - "/docs/tech/llmops/langsmith/"
---

LangSmith는 앱 실행을 추적하고 데이터셋, 실험, 평가와 연결하는 플랫폼입니다. LangChain, LangGraph의 실행 트리와 자연스럽게 연결되지만 이 프레임워크에만 제한되지는 않습니다. Bookway에서는 후속 질문과 도구 경로의 실패를 좁히는 선택지입니다.

## trace를 읽는 순서

“그 주문은 언제 도착하나요?”에 잘못 답했다면 마지막 모델 출력부터 고치지 않습니다. 이전 대화의 주문 선택, 서버 소유권 검사, 도구 입력, 원천 상태와 생성 문맥을 순서대로 봅니다. 체크포인트가 있어도 다른 고객의 thread에 접근할 수 없어야 합니다.

추적을 켜면 입력, 출력이 원격 서버에 전송될 수 있습니다. 승인된 프로젝트, endpoint, 저장 범위를 먼저 구성하고, 원문 마스킹은 SDK로 넘기기 전에 적용합니다.

## 프레임워크 밖의 작은 작업 추적

`LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` 등 승인된 환경 설정과 `langsmith` SDK를 전제로 합니다. endpoint가 필요한 배포에서는 승인된 주소도 지정합니다.

```python
from langsmith import traceable

@traceable(name="bookway-source-selection", run_type="chain")
def source_selection(question: str) -> dict:
    return {
        "question": question,
        "release_id": "help-r8",
        "allowed_sources": ["returns-v3#1"],
    }

source_selection("Synthetic Bookway return-policy question")
```

이 조각은 trace 연결용 합성 작업이지 실제 retrieval은 아닙니다. LangChain 자동 tracing과 함께 쓰면 중복 루트가 생기지 않도록 부모 실행 context를 전달합니다. 비동기, 큐 경계를 넘어갈 때도 같은 요청의 인과관계를 유지해야 합니다.

## 데이터셋과 실험의 연결

| 단계 | Bookway에서 고정할 값 |
| --- | --- |
| 사례 생성 | 합성 질문, 기대 source, 허용 도구, 거절 조건 |
| 후보 실행 | release, 모델, prompt, retriever revision |
| 평가 | 인용 정확성, 내용 기준, 경로, 비용, 지연 |
| 오류 분석 | 어떤 사례, 고객 구간에서 악화됐는지 |
| 승인 | 예산, 권한 조건까지 확인한 출시 결정 |

동일 데이터셋 버전에서 `help-r7`과 `help-r8`을 실행하고 case별 차이를 봅니다. 평균 score만 좋아져도 주문 소유권 같은 필수 조건이 한 건 실패하면 출시를 막을 수 있습니다. evaluator의 모델, 지침도 버전 관리합니다.

## Langfuse와 함께 쓸 때

둘 다 trace, 평가, 프롬프트 기능이 겹칩니다. Bookway의 기본 관측 경로를 하나 정하고 조직의 권한, 가격, 배포 제약, 프레임워크 통합으로 선택합니다. 모두 켜서 토큰 원문을 여러 곳에 복제하는 것은 기본값이 아닙니다.

추적 서비스 장애와 앱 장애를 분리하고, 운영의 필수 감사 기록은 별도 내구성 경로를 검토합니다. 외부 UI에서 trace를 삭제하는 것과 원천 로그, 백업의 삭제는 보존 정책상 다른 작업입니다.

[공식 observability](https://docs.langchain.com/langsmith/observability) / [tracing 시작](https://docs.langchain.com/langsmith/observability-quickstart) / [프롬프트, trace 대안](/docs/tech/ops/llmops/langfuse/)
