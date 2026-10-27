---
title: "NeMo Guardrails: 대화와 행동 경로의 통제"
description: "Bookway의 입력, 검색, 행동, 출력 정책을 guardrail 흐름으로 구성"
date: 2026-10-25T08:43:00+09:00
weight: 115
tags: ["llmops", "nemo-guardrails", "safety"]
aliases:
  - "/docs/tech/llmops/nemo-guardrails/"
---

NeMo Guardrails는 모델, rail, 대화 흐름, custom action으로 실행 경로를 통제한다. 구조 검증 중심의 [Guardrails AI](/docs/tech/ops/llmops/guardrails/)와 제품 및 API가 다르다.

## Bookway의 정책 배치

```text
입력 rail: 서비스 범위, 민감정보 처리
  → 검색 rail: 허용된 정책, 유효 시점
  → 대화/행동 흐름: 주문 확인, 반품 조건, 승인
  → 외부 도구: 서버 권한, 멱등 실행
  → 출력 rail: 근거, 유출, 안내 형식
```

정책 문서는 신뢰할 지시문이 아니라 외부 데이터이다. 검색 문서 안의 명령을 시스템 정책으로 실행하지 않는다. 문서, 도구 결과의 출처와 신뢰 경계를 보존한다.

## 구성 파일과 실행 연결

구성 디렉터리에는 선택한 버전의 `config.yml`, 필요 시 Colang flow, 모델별 prompt, custom action을 둔다. LLM endpoint, 인증, 사용 rail은 배포 환경에 맞게 설정한다. Colang 세대와 예제가 서로 다를 수 있어 한 버전의 schema로 통일한다.

다음은 **이미 검증한 rail 설정이 존재하는 환경**에서 앱에 연결하는 Python 진입점이다. 이 코드만으로 어떤 guard도 활성화되지 않으며 실제 검사는 설정에 달려 있다.

```python
from nemoguardrails import LLMRails, RailsConfig

config = RailsConfig.from_path("bookway_rails")
rails = LLMRails(config)
response = rails.generate(messages=[{
    "role": "user",
    "content": "Synthetic question about the Bookway return policy.",
}])
print(response)
```

검증된 config와 모델을 release에 포함하고 서버 시작 시 로딩 실패를 드러낸다. 빈 설정이나 모델 접속 오류를 “rail을 생략한 정상 응답”으로 바꾸지 않는다.

## 반품 행동의 통제

대화에서 승인을 물었다는 사실만으로 거래 API를 실행하지 않는다. 서버가 주문 소유권, 반품 가능 조건, 승인 대상 지문, 만료를 확인하고, 승인한 인자와 같은 요청만 실행한다. custom action에는 최소 권한의 client를 주며 모델이 endpoint나 자격 증명을 선택하게 하지 않는다.

입력/출력 moderation 모델과 거절 경로도 정상 문의, 경계 문의, 다국어, 도구 오류로 평가한다. 추가 모델 호출은 비용과 TTFT를 늘릴 수 있어 rail별 span으로 측정한다.

## 도입 판단

단순한 JSON schema 검사는 일반 validation 코드가 더 단순할 수 있다. 대화 정책, 행동 순서, 여러 모델 기반 검사 흐름을 명시적으로 관리할 필요가 있을 때 도입한다. 안전 모델의 낮은 위험 점수가 DB 접근 권한을 부여하지 않으며, 알려진 몇 사례의 통과가 모든 우회를 막는다는 뜻도 아니다.

[공식 구성 가이드](https://docs.nvidia.com/nemo/guardrails/configure-guardrails/configure-rails) / [설치, 전제](https://docs.nvidia.com/nemo/guardrails/get-started/installation-guide) / [행동 승인 구조](/docs/tech/ops/llmops/application/)
