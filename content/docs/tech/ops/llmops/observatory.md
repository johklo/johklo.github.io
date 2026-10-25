---
title: "Observatory 기록: 관측에서 개선 루프로"
description: "기존 LLMOps 글의 2026년 4월 관측 플랫폼 분석과 Bookway에 적용할 책임 구분"
date: 2026-04-13T12:00:00+09:00
lastmod: 2026-10-25T08:43:00+09:00
weight: 140
tags: ["llmops", "observability", "evaluation"]
aliases:
  - "/docs/tech/llmops/observatory/"
---

기존 LLMOps 글에는 Observatory를 만들면서 관측과 평가의 차이를 정리한 기록이 있었습니다. 아래는 **2026년 4월 당시 글의 분석**을 보존한 것입니다. 현재 제품 구현 상태나 당시 계획의 완료 여부를 검증한 자료는 아닙니다.

## 당시의 구조

목표는 프로덕션 LLM 앱을 디버깅, 평가, 개선하는 운영 가시성이었습니다. Azure Application Insights의 OpenTelemetry 데이터를 KQL로 읽고, trace, waterfall, 도구 호출, 비용을 보는 방향으로 정리했습니다.

관측이 있다는 사실과 출시 결정을 신뢰할 수 있다는 사실은 달랐습니다. 당시 기록에서는 단어 겹침 기반 품질 휴리스틱을 의미적 근거성 판정으로 사용하기 어렵다는 점, 사용자 피드백, 검토 큐, 평가 데이터셋으로 이어지는 경로가 부족하다는 점을 남겼습니다.

| 당시 분석한 빈틈 | Bookway에서 필요한 연결 |
| --- | --- |
| 응답을 볼 수 있지만 실패 유형이 없음 | 검색, 생성, 권한, 도구, 지연으로 분류 |
| 휴리스틱 점수만 있음 | 결정적 계약 + 평가자 + 사람 판정 비교 |
| 운영 사례가 실험으로 안 돌아옴 | 비식별 재현 사례를 평가집에 추가 |
| 평가가 배포를 막지 못함 | 후보 지문과 결합한 CI 게이트 |
| 대시보드와 release가 분리됨 | 구체 문서, prompt, 모델, 코드 기록 |

## Bookway에 적용하는 기준

```text
OTel / 실행 trace
  → 실패 발견
  → 담당자 검토, 합성 재현
  → 고정 평가집
  → 변경 후보 평가
  → 승인, 출시, 관측
```

관측 데이터를 Azure 안에 둔다고 앱 전체 데이터가 자동으로 그 경계 안에 머무는 것은 아닙니다. 모델 endpoint, 평가자, 로그 exporter, 백업까지 확인해야 합니다. 반대로 외부 SaaS를 쓰지 않는다는 이유만으로 보존, 접근 정책을 생략할 수는 없습니다.

운영 성숙도는 특정 도구의 설치 수나 임의의 레벨보다, 이 루프가 실제 변경과 실패에서 유지되는지로 판단하는 편이 구체적입니다. Bookway 가이드에서는 [OTel](/docs/tech/ops/llmops/opentelemetry/), [trace, 피드백](/docs/tech/ops/llmops/langfuse/), [평가](/docs/tech/ops/llmops/promptfoo/), [출시 계약](/docs/tech/ops/llmops/release/)을 이 책임으로 나눴습니다.

[기존 주소를 유지한 LLMOps 상위 글](/docs/tech/ops/llmops/) / [MLOps 관측 경로](/docs/tech/ops/mlops/monitoring/)
