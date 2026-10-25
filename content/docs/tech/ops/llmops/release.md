---
title: "Bookway 출시 계약: 평가, 승인, 점진 배포, 복구"
description: "검색, 프롬프트, 모델, 도구, 캐시를 한 release로 고정하고 실패 지점별로 복구"
date: 2026-10-25T08:43:00+09:00
weight: 130
tags: ["llmops", "release", "governance", "mlops"]
aliases:
  - "/docs/tech/llmops/release/"
---

같은 포장에 재료만 몰래 바꾸면 검사 결과를 믿을 수 없습니다. Bookway의 출시 단위는 이미지 하나가 아니라 **평가한 데이터, 설정, 모델, 실행 정책의 조합**입니다. 도구별 성공을 전체 출시 성공으로 합산하지 않습니다.

## 설명용 불변 manifest

```json
{
  "release_id": "help-r8",
  "application_revision": "bookway-app-r8",
  "policy_snapshot": "policy-v3",
  "index": "bookway_policy_v3",
  "embedding_revision": "bookway-embedding-r2",
  "retrieval_config": "retrieval-r4",
  "prompt_version": 12,
  "model_deployment": "bookway-chat-r3",
  "tool_schema": "orders-v2",
  "guardrail_config": "rails-r2",
  "evaluation_dataset": "help-eval-v5",
  "cache_namespace": "help-r8-public-policy",
  "recommendation_release": "rec-r17"
}
```

이는 Bookway 가상의 식별자 계약입니다. 실제 빌드에서는 가변 이름 대신 해석된 digest, commit, snapshot 지문을 함께 저장합니다. private endpoint와 자격 증명은 manifest에 넣지 않습니다.

## 변경 종류별 실행 범위

| 변경 | 다시 확인할 것 | 복구 대상 |
| --- | --- | --- |
| 정책 개정 | 적용일, 삭제, 검색, 인용, 캐시 | 유효한 정책 조합, 단순 옛 정책 아님 |
| embedding 변경 | 전체 재색인, 질의 호환, recall | 인덱스와 질의 모델 함께 |
| prompt 변경 | 예외, 거절, 도구 경로, 비용 | 구체 prompt와 실행 설정 |
| 모델/provider 변경 | schema, tool, 언어, 지연 | 승인된 deployment 조합 |
| 주문 도구 변경 | 소유권, 인자, 멱등, 장애 | API 호환, 거래 복구 |

정책상 더는 유효하지 않은 답을 “이전 release라 안정적”이라는 이유로 돌려주면 안 됩니다. 코드 rollback과 업무 정책 복구는 다른 판단입니다.

## 평가에서 배포까지

먼저 source ID, 권한, schema, 행동 승인 같은 필수 검사를 통과해야 합니다. 그다음 Promptfoo, DeepEval, Ragas 중 목적에 맞는 평가로 품질을 비교합니다. 평균 품질, 구간별 회귀, TTFT, 전체 시간, 비용, 관측 누락까지 보고 승인합니다.

평가 보고서는 실행한 release 지문과 결합하고, 오래된 보고서를 새 후보에 재사용하지 않습니다. 평가자 장애, 예산 초과, 미완료 사례는 “품질 통과”가 아닙니다. 학습이나 prompt 수정에 사용한 질문과 최종 보류 평가집을 구분합니다.

배포는 새 release 준비 → 로딩, 의존성 검사 → 제한된 트래픽 → 관측 → 확대 순서입니다. traffic splitting은 별도 라우터, 배포 controller가 수행하며 Langfuse label 이동만으로 카나리 배포가 완성되지는 않습니다.

## 거래와 checkpoint의 장애 창

```text
승인 전 중단             → 부작용 없이 종료
승인 후 실행 전 중단     → 대상, 만료, 조건 재검사
거래 요청 후 응답 유실   → 업무 키로 실제 처리 상태 조회
거래 성공 후 상태 유실   → 기존 결과를 복원, 새 거래 생성 금지
```

LangGraph checkpoint, MCP request ID, 거래 멱등 키는 서로 다른 수명입니다. 외부 효과를 정확히 한 번 실행하려면 원천의 멱등 지원, 입력 일치 검사, 동시성 제약, 결과 조회가 필요합니다.

## 운영 책임과 피드백

앱 팀은 질문, 도구 경로, 데이터 팀은 정책, 색인, 플랫폼 팀은 실행, 비용, 관측, 업무 담당자는 정책, 승인을 맡도록 변경 소유자를 명시합니다. 소규모 팀에서 사람이 겸임해도 책임은 나눌 수 있습니다.

실패 trace → 검토, 비식별 사례 → 평가집 → 후보 → 승인 → 배포의 루프를 유지합니다. 기존 LLMOps 글의 프롬프트 버전, 품질/비용/지연, 인간 감독을 이 실행 계약으로 구체화했습니다.

[MLOps 출시 경로](/docs/tech/ops/mlops/gitops/) / [LLMOps 전체 지도](/docs/tech/ops/llmops/) / [기존 RAG 출시, 복구 실습](/docs/tech/ops/mlops/labs/ml-platform-labs-10-rag-release/)
