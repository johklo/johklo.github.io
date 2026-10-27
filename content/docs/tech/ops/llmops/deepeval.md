---
title: "DeepEval: 답변의 의미와 실행 경로 평가"
description: "Bookway 응답의 근거성, 업무 기준을 평가자와 결정적 검사로 분리"
date: 2026-10-25T08:43:00+09:00
weight: 65
tags: ["llmops", "deepeval", "evaluation"]
aliases:
  - "/docs/tech/llmops/deepeval/"
---

DeepEval은 응답, 문맥, 기대 기준을 test case로 만들어 의미를 평가한다. 많은 metric이 LLM-as-a-judge를 사용하므로 평가자도 틀릴 수 있다.

## Bookway에서 나누는 판정

구조, 출처 ID, 권한, 도구 인자는 일반 코드로 검사하고, 사실의 지지 여부, 설명의 완전성은 평가 지표로 본다. “정책에는 7일, 답에는 30일”처럼 명확한 위반은 높은 다른 점수로 상쇄하지 않는다.

다음은 `deepeval`과 승인된 평가자 접속이 준비된 환경의 합성 사례이다. `BOOKWAY_JUDGE_MODEL`에 사용 가능한 평가자 모델 이름을 지정하며 모델 제공자 인증이 별도 필요하다. 실행하면 문맥과 응답이 평가자에게 전달된다.

```python
import os
from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase

case = LLMTestCase(
    input="What is the Bookway return window?",
    actual_output="Eligible printed books can be returned within 7 days.",
    retrieval_context=[
        "Synthetic policy-v3: eligible printed books may be returned "
        "within 7 days. Digital products are excluded."
    ],
)
metric = FaithfulnessMetric(
    model=os.environ["BOOKWAY_JUDGE_MODEL"],
    threshold=0.8,
    include_reason=True,
)
metric.measure(case)
print(metric.score, metric.reason)
```

`0.8`은 연결 예시이지 검증된 출시 기준이 아니다. 실제 threshold는 사람의 판정과 비교해 정하고, 점수뿐 아니라 이유, 오류, 평가자 버전을 남긴다. 위 코드는 평가 연결용이며 Bookway 서비스가 생성한 실제 출력은 아니다.

## Faithfulness와 정확성의 차이

근거성은 **주어진 문맥이 답을 지지하는지**이다. 검색 문맥 자체가 오래된 `policy-v2`라면 답이 그 문맥에 충실해도 현재 정책에는 틀릴 수 있다. 적용일, 문서 버전, 출처의 올바름은 별도 계약으로 검사한다.

G-Eval 같은 rubric 평가에는 “전자책 예외를 유지하고 불확실한 조건을 만들지 않음”처럼 Bookway 업무 기준을 적다. 말투, 친절함과 정책 정확성을 하나의 모호한 “좋음” 점수로 합치지 않는다.

## 에이전트 평가와 운영

도구 선택, 인자 정확성과 전체 task completion을 구분한다. 주문 답이 맞아도 다른 고객 도구를 호출했다면 실패이다. 같은 질문을 반복 실행해 분산, 비용을 보고, 평가자가 처리하지 못한 사례는 0 또는 통과로 조용히 대체하지 않는다.

평가 결과를 [Promptfoo](/docs/tech/ops/llmops/promptfoo/)나 CI 보고서에 연결할 수 있지만 같은 질문을 여러 평가 도구로 반복 측정하는 비용도 계산한다. 평가자는 필수 인증, 권한, 승인 규칙을 면제할 수 없다.

[공식 Faithfulness 문서](https://deepeval.com/docs/metrics-faithfulness) / [metric 개요](https://deepeval.com/docs/metrics-introduction) / [검색 실패 진단](/docs/tech/ops/llmops/ragas/)
