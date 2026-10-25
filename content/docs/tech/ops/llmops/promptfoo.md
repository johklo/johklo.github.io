---
title: "Promptfoo: 실제 서비스 경로의 회귀 평가"
description: "Bookway의 질문, 기대 조건, provider를 고정하고 CI 출시 판정에 연결"
date: 2026-10-25T08:43:00+09:00
weight: 60
tags: ["llmops", "promptfoo", "evaluation"]
aliases:
  - "/docs/tech/llmops/promptfoo/"
---

새 안내 문구를 만들 때 예쁜 문장 하나만 보면 반품 예외를 놓칠 수 있습니다. Promptfoo는 여러 입력, 후보, assertion을 같은 방식으로 실행하고 비교하는 평가 도구입니다. Bookway에서는 프롬프트 변경뿐 아니라 실제 검색, 도구 경로의 회귀를 관리합니다.

## 단위 평가와 서비스 평가

프롬프트만 모델에 보내는 시험은 검색기, 권한, 캐시를 우회합니다. 운영 release를 평가하려면 provider가 **고정 `help-r8` endpoint**를 호출하고 실제 답, 출처, 오류 상태를 반환해야 합니다. 먼저 작은 prompt 단위 검사를 둔 뒤 서비스 평가를 추가합니다.

아래 `promptfooconfig.yaml`은 Ollama가 로컬에서 실행 중이고 `llama3.2:latest`가 준비된 경우의 합성 분류 예제입니다. `npx promptfoo`를 쓰기 전 프로젝트의 검증한 Promptfoo 버전을 package lock에 고정합니다.

```yaml
description: Bookway synthetic routing contract
prompts:
  - "Classify this request. Return only policy or order: {{question}}"
providers:
  - ollama:chat:llama3.2:latest
tests:
  - vars:
      question: "What is the return policy?"
    assert:
      - type: equals
        value: policy
  - vars:
      question: "Where is my order?"
    assert:
      - type: equals
        value: order
```

```powershell
npx promptfoo eval --config promptfooconfig.yaml
```

이 구성은 분류 프롬프트의 단위 평가이며, 정책 검색, 주문 권한, 실제 서비스 품질을 검증하지 않습니다. 운영 모델은 가변 태그 대신 release가 해석한 구체 버전을 기록합니다.

## Bookway의 실제 평가집

| 사례 | 결정적 검사 | 의미 검사 |
| --- | --- | --- |
| 일반 반품 기간 | 유효 source ID, release | 날짜, 적용 조건 유지 |
| 전자책 예외 | 금지 도구 미호출 | 예외를 일반 도서와 구분 |
| 근거 없는 질문 | 근거 부족 상태 | 허위 정책 생성 여부 |
| 다른 고객 주문 | 서버 접근 거절 | 원문, 상태 노출 없음 |
| 주문 API 장애 | 오류 상태, 재시도 한도 | “주문 없음”과 구분 |

출처, 도구 ID, HTTP 상태는 문자열 유사도 대신 구조적으로 검사합니다. 문체, 의미는 rubric이나 별도 평가자를 사용하되 평가자 모델, 프롬프트, 재시도까지 기록합니다. 예시 threshold는 조직의 위험 기준을 대신하지 않습니다.

## CI에 연결하기

평가 입력, 실행 release, 보고서의 해시를 묶고, 평가 실패와 실행 자체의 실패를 모두 출시 차단으로 연결합니다. 단일 평균 통과 대신 권한 위반 0건 같은 필수 조건과 일반 품질 조건을 분리합니다. 유료 평가 모델을 사용하면 PR별 예산과 동시성을 제한합니다.

Promptfoo의 red teaming도 보완 경로입니다. 합성 환경, 허가된 endpoint에서 수행하고 외부 도구의 실제 부작용은 차단합니다. 몇 가지 시험 통과가 보안 보증은 아닙니다.

[공식 assertion 문서](https://www.promptfoo.dev/docs/configuration/expected-outputs/) / [기존 실제 RAG 연결 기록](/docs/tech/ops/mlops/labs/ml-platform-labs-10-rag-release/) / [출시 게이트](/docs/tech/ops/llmops/release/)
