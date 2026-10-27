---
title: "Ragas: 검색과 생성의 실패를 분리"
description: "Bookway 정책의 기대 근거, 검색 문맥, 답변을 분리해 색인 변경을 평가"
date: 2026-10-25T08:43:00+09:00
weight: 70
tags: ["llmops", "ragas", "rag-evaluation"]
aliases:
  - "/docs/tech/llmops/ragas/"
---

Ragas는 RAG의 검색과 생성을 나눠 평가한다. Bookway에서는 chunk 크기, embedding, reranker, top-k 변경의 원인을 좁히는 데 쓴다.

## 평가 행의 계약

한 사례에는 `case_id`, 질문, 기대 정책 버전, source ID, 검색한 원문, 실제 응답, 필요한 reference를 저장한다. metric마다 필요한 필드가 다르므로 모든 지표를 “정답 없이 가능”으로 묶지 않는다.

| 관찰 | 의미 | 우선 변경할 곳 |
| --- | --- | --- |
| 기대 source를 못 찾음 | 검색 recall 문제 | 분할, embedding, filter, 후보 수 |
| 관련 없는 문맥이 많음 | precision, 문맥 예산 문제 | 재정렬, 중복 제거 |
| 문맥은 맞고 예외를 누락 | 생성, 완전성 문제 | 지침, 모델, 출력 검사 |
| 오래된 정책에 충실한 답 | 근거 선택의 유효성 문제 | release, 적용일 |

## 근거성 평가 연결

아래는 공식 문서의 collections API 계열을 사용한다. `ragas`, `openai` 환경과 승인된 평가 endpoint, 인증, `BOOKWAY_JUDGE_MODEL`이 필요하다. 자체 OpenAI-compatible 평가자를 쓰면 해당 SDK 설정과 호환성을 먼저 확인한다.

```python
import asyncio
import os
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

async def main():
    client = AsyncOpenAI()
    judge = llm_factory(os.environ["BOOKWAY_JUDGE_MODEL"], client=client)
    scorer = Faithfulness(llm=judge)
    result = await scorer.ascore(
        user_input="What is the return window for printed books?",
        response="Eligible printed books have a 7-day return window.",
        retrieved_contexts=[
            "Synthetic policy-v3: eligible printed books have "
            "a 7-day return window; digital products are excluded."
        ],
    )
    print(result.value)
    await client.close()

asyncio.run(main())
```

이는 합성 평가 입력이며 실제 서비스 품질 수치가 아니다. 오래된 `SingleTurnSample` 예제와 새로운 collections API를 섞지 않고 선택한 Ragas 버전을 lockfile에 고정한다.

## 후보를 비교하는 실무 절차

현재 `help-r7`과 후보 `help-r8`을 같은 문서 snapshot, 질문 집합에서 실행한다. 검색된 source ID 기준의 결정적 recall과 의미 지표를 따로 계산한다. retrieval top-k가 늘면 비용, 잡음도 늘므로 문맥 토큰, 지연까지 함께 비교한다.

답을 못 찾는 질문, 정책 예외, 접근 불가 문서도 포함한다. synthetic testset을 생성할 수 있지만 같은 생성 모델이 만든 질문만으로 평가하면 실제 문의의 어려움을 놓칠 수 있어 검토된 운영 유형을 보완한다.

metric의 평균보다 case별 악화와 원인을 확인한다. 평가자 실패, 빈 문맥, 판정 불가를 성공 집합에서 조용히 빼지 않는다. 근거성 점수가 실제 정책의 법적, 업무적 정확성을 보장하지는 않는다.

[공식 metric 개요](https://docs.ragas.io/en/stable/concepts/metrics/overview/) / [Faithfulness API](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/) / [문서 파이프라인](/docs/tech/ops/llmops/ingestion-faiss/)
