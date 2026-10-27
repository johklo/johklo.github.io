---
title: "Guardrails AI: 구조와 도메인 규칙을 실행 경계에서 검사"
description: "Bookway 모델 출력의 JSON, 필드, 근거, 정책 위반을 명시적으로 처리"
date: 2026-10-25T08:43:00+09:00
weight: 110
tags: ["llmops", "guardrails", "validation"]
aliases:
  - "/docs/tech/llmops/guardrails/"
---

Guardrails AI는 입출력 guard, validator, 구조화된 생성을 구성한다. Bookway에서는 모델 응답을 도구나 UI에 전달하기 전 검증 계층으로 둔다.

## 검사를 세 층으로 분리하기

| 층 | Bookway 검사 | 실패 의미 |
| --- | --- | --- |
| 형식 | JSON, 필수 필드, 타입 | 응답 해석 실패 |
| 도메인 | 허용 source ID, status, 값 범위 | 앱 계약 위반 |
| 의미, 안전 | 정책 예외, 민감정보, 근거 | 잘못된 내용 또는 위험 |

지원 source 목록은 검색 결과에서 프로그램이 만들며 모델이 임의로 추가할 수 없다. 구조 검사에 통과한 `status="approved"`도 실제 반품 승인 권한을 갖지 않는다.

## validator 연결 예제

2026-10-25 확인한 공식 저장소는 validator의 일반 PyPI 패키지 설치로의 이전과 hosted remote inference 중단을 안내한다. 오래된 Hub 설치, 원격 호출 전제 코드를 그대로 쓰지 않고 선택 버전의 migration을 확인한다.

아래는 `guardrails-ai`, `guardrails-ai-regex-match`가 설치된 환경에서 release ID 형식만 검사하는 예제이다.

```python
from guardrails import Guard, OnFailAction
from guardrails_ai.regex_match import RegexMatch

release_guard = Guard().use(
    RegexMatch,
    regex=r"^help-r[0-9]+$",
    on_fail=OnFailAction.EXCEPTION,
)
release_guard.validate("help-r8")
```

이 검사는 문자열 형식만 보며 `help-r8`이 승인되었는지 확인하지 않는다. 승인 목록은 서버의 release 저장소에서 검사한다. 선택한 validator가 모델 다운로드, 외부 inference를 사용하는지도 설치 전에 확인한다.

## 실패 처리와 재질의

validator 실패를 빈 답이나 정상 status로 바꾸지 않는다. 형식 오류는 제한된 재질의로 복구할 수 있지만, 접근 권한, 금지 행동은 prompt를 반복해 우회하지 않는다. retry 횟수, 총 토큰, 전체 deadline을 함께 제한한다.

출력 전 검사라면 검증을 마친 값만 UI와 도구에 전달한다. 이미 스트리밍한 원문은 나중에 취소해도 사용자가 읽었을 수 있으므로 민감정보 위험과 스트리밍 정책을 별도로 설계한다.

## 운영 지표와 한계

정상 응답의 오차단률, 위험 응답의 미차단률, 검증 p95, 외부 호출 비용, 실행 오류를 측정한다. classifier, regex, LLM judge는 각각 다른 한계를 가진다. Guardrails 서비스 장애를 “검사 통과”로 처리하지 않고 위험도에 따라 거절, 제한 응답, 승인된 대체 경로를 사용한다.

대화 순서와 행동 정책을 구성하는 [NeMo Guardrails](/docs/tech/ops/llmops/nemo-guardrails/)와 기능이 일부 겹친다. 둘을 동시에 도입하기보다 어느 경계의 어떤 실패를 막을지 정하고, 인증, 소유권, 거래 승인은 일반 서버 코드에서 강제한다.

[공식 Guardrails 저장소](https://github.com/guardrails-ai/guardrails) / [프레임워크 개요](https://guardrailsai.com/docs) / [Bookway 도구 계약](/docs/tech/ops/llmops/application/)
