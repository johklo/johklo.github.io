---
title: "BentoML: 추천 모델을 서비스로 만드는 경계"
description: "모델 로딩, 입력 계약, 배치, 패키징, 롤아웃을 Bookway API에 적용"
date: 2026-10-25T08:43:00+09:00
weight: 50
tags: ["mlops", "bentoml", "serving"]
aliases:
  - "/docs/tech/mlops/bentoml/"
---

모델이 조리법이라면 BentoML Service는 주문을 받고 음식을 내는 주방입니다. 모델의 `predict()` 외에 **입력 검증, 피처 조회, 전처리, 실행 자원, 응답 형식**이 필요합니다. Bento는 서비스를 묶는 패키지이고 BentoCloud는 관리형 배포 선택지입니다.

## Bookway 추천 API의 처리 순서

```text
인증된 고객
  → 요청 schema / 후보 수 제한
  → Feast 조회 / 누락, 최신성 검사
  → 모델 17의 전처리와 점수 계산
  → 품절, 허용 범위 필터
  → book_id 순위 + rec-r17 + fallback_reason
```

MLflow에서 승인한 모델을 BentoML Model Store로 가져오거나 명시적인 artifact로 로딩합니다. 시작 때 바뀔 수 있는 alias 대신 `rec-r17`의 고정 참조를 해석합니다. 모델이 로딩되지 않았는데 readiness를 성공시키면 첫 고객 요청이 초기화 비용과 실패를 떠안습니다.

## Service의 최소 경계

아래는 현재 데코레이터 방식의 BentoML에서 합성 후보 ID의 계약만 노출하는 독립 예제입니다. **추천 모델, Feast, 인증은 포함하지 않으며 추천 품질을 보여 주는 코드가 아닙니다.** `service.py`로 두고 실행합니다.

```python
import bentoml
from pydantic import BaseModel, Field

class RankRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=100)

class RankResponse(BaseModel):
    candidate_count: int
    release_id: str

@bentoml.service
class BookwayContract:
    @bentoml.api
    def validate(self, request: RankRequest) -> RankResponse:
        if len(set(request.candidate_ids)) != len(request.candidate_ids):
            raise ValueError("Duplicate candidates")
        return RankResponse(
            candidate_count=len(request.candidate_ids),
            release_id="contract-only",
        )
```

```powershell
bentoml serve service:BookwayContract
```

실제 `rank` 메서드는 앞의 순서대로 구성하며 호출당 남은 마감 시간을 Feast, 모델 단계에 나눕니다. 내부 검증 예외와 client/server 오류의 HTTP 매핑은 배포한 BentoML 버전의 error handling에 맞춰 명시적으로 테스트합니다.

## 패키징과 성능

Service, 모델 참조, Python 의존성, 시스템 패키지를 배포 명세에 넣고 Bento를 빌드합니다. `bentoml build`와 `bentoml containerize` 이후에도 모델 다운로드, 초기화, 동시 요청을 별도로 확인합니다. 비밀키를 Bento나 컨테이너 레이어에 넣지 않습니다.

배치는 처리량을 높일 수 있지만 기다리는 요청에는 지연을 더합니다. GPU 생성 모델과 작은 CPU 추천 모델의 최적 설정은 다릅니다. 후보 수별 지연, p95, 동시성, 메모리를 측정하고, 무제한 큐 대신 과부하를 명시적으로 거절합니다.

## 출시와 복구

새 배포를 준비한 뒤 소량 트래픽에서 구체 release와 오류율을 비교합니다. 모델만 바꾸지 않고 Feast 계약, 전처리, 응답 schema가 맞는지 확인합니다. rollback 대상은 모델 파일 하나가 아니라 `rec-r16`의 전체 서비스 조합입니다.

LLMOps에서도 BentoML로 임베딩, 재정렬, 생성 서비스를 감쌀 수 있습니다. 다만 [vLLM](/docs/tech/ops/llmops/vllm/)의 추론 엔진과 [LiteLLM](/docs/tech/ops/llmops/litellm/)의 게이트웨이 역할을 자동으로 대체하는 것은 아닙니다.

[공식 Service 문서](https://docs.bentoml.com/en/latest/build-with-bentoml/services.html) / [모델 로딩 문서](https://docs.bentoml.com/en/latest/build-with-bentoml/model-loading-and-management.html) / [기존 기능 정리](/docs/tech/ops/mlops/labs/bentoml-capabilities/)
