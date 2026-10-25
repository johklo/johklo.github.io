---
title: "Langfuse: trace·프롬프트·피드백을 연결"
description: "Bookway의 정책 답변을 재현 가능한 실행 기록과 다음 평가로 연결"
date: 2026-10-25T08:43:00+09:00
weight: 50
tags: ["llmops", "langfuse", "observability"]
---

영수증에 총액만 있으면 어떤 품목 때문에 비싸졌는지 알 수 없습니다. Langfuse는 질문 하나에서 검색·생성·도구 호출이 어떻게 이어졌는지 기록하는 LLM 관측 도구입니다. 프롬프트 관리·평가·피드백과 연결할 수 있지만 기록만으로 답의 진위를 보장하지 않습니다.

## Bookway trace의 구조

```text
help request / help-r8
  ├─ retrieve: policy-v3, 검색 질의, 허용된 source ID
  ├─ rerank: 모델 revision, 후보 수
  ├─ generate: 프롬프트 12, 모델 배포, 토큰·시간
  ├─ validate: 출처·schema·정책 검사
  └─ feedback: 유형·검토 결과
```

검색 문서와 실제 생성 문맥을 따로 남겨야 “검색은 맞고 문맥 조립이 틀린 경우”를 찾을 수 있습니다. 고객 원문 대신 합성 사례·문서 ID·길이·지문만 남기는 정책도 가능합니다.

## SDK를 붙이는 최소 단위

승인된 Langfuse 배포에 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`이 설정된 SDK 환경에서 다음처럼 일반 작업 span을 만들 수 있습니다. **실행하면 설정한 서버로 기록이 전송**되므로 개발 합성 자료에만 적용합니다.

```python
from langfuse import get_client, observe

@observe(name="bookway-policy-request")
def describe_release(release_id: str) -> dict:
    return {"release_id": release_id, "policy_version": "policy-v3"}

describe_release("help-r8")
get_client().flush()
```

모델 SDK wrapper나 프레임워크 callback을 추가하면 generation 기록을 더 연결할 수 있습니다. wrapper와 수동 span이 같은 호출을 중복 기록하지 않게 합니다. 서버 종료 시 flush·종료 정책을 두되 추적 장애를 고객 요청의 무한 대기로 만들지 않습니다.

## 프롬프트를 출시 단위로 고정하기

Langfuse의 production label은 가변 포인터입니다. 개발에서 프롬프트 12를 평가했다면 `help-r8`에는 구체 버전·변수 schema·fallback 정책을 저장합니다. label을 옮기는 작업도 승인된 출시 변경이어야 합니다.

프롬프트 fetch 실패 때 코드의 아무 문자열로 조용히 대체하면 평가한 것과 다른 서비스가 됩니다. 승인된 로컬 snapshot을 명시적으로 사용하거나 해당 경로를 실패 처리하고, 어떤 버전을 썼는지 남깁니다.

## 피드백을 평가로 돌려보내기

낮은 점수의 trace를 검토해 검색 누락·잘못된 정책·생성 오류·지연으로 분류합니다. 개인정보를 제거한 재현 사례를 고정 평가집에 넣고 새 release를 비교합니다. 사용자의 싫어요 하나를 곧바로 정답 label로 보지는 않습니다.

Cloud와 self-host 모두 접근 제어·원문 저장 범위·삭제·백업·retention을 정해야 합니다. 외부 수집이 허용되지 않으면 자체 배포나 승인된 [OTel 수집 경로](../opentelemetry/)를 사용합니다. 추적 누락률도 운영 지표로 두어 “보이지 않는 요청”을 파악합니다.

[공식 관측 개요](https://langfuse.com/docs/observability/overview) / [SDK 시작](https://langfuse.com/docs/observability/get-started) / [LangSmith와 비교](../langsmith/)
