---
title: "Evidently: 데이터 변화와 모델 품질을 분리"
description: "기준 집합, 현재 집합, 지연 정답으로 Bookway 운영 변화를 진단"
date: 2026-10-25T08:43:00+09:00
weight: 90
tags: ["mlops", "evidently", "data-drift"]
aliases:
  - "/docs/tech/mlops/evidently/"
---

Evidently는 입력, 예측, 정답 변화를 비교하며 경고만으로 재학습하지 않는다.

## 무엇을 비교할지 먼저 고정하기

`rec-r17` 검증 기간의 피처를 reference로, 출시 이후 같은 조건의 피처를 current로 둔다. 신규 고객 비중이 높은 주말과 기존 고객 중심 평일을 섞으면 분포 차이의 원인을 모델로 오해할 수 있다.

| 검사 | 입력 | 의미 |
| --- | --- | --- |
| 데이터 품질 | 누락, 범위, schema | 수집 또는 변환 이상 |
| 피처 drift | 기준/현재 피처 | 고객, 상품, 환경의 변화 |
| 예측 drift | 기준/현재 점수 | 입력 또는 모델 경로 변화 |
| 실제 품질 | 예측, 노출, 지연 정답 | 업무 목표의 변화 |

추천 NDCG 같은 업무 평가는 별도 랭킹 평가 코드가 필요할 수 있다. Evidently의 일반 drift 점수를 NDCG로 바꿔 해석하지 않는다.

## 보고서 생성 경로

다음은 최신 Dataset/Report 계열 API의 합성 입력 예제이다. 기존 실습의 고정 버전과 API가 다를 수 있으므로 프로젝트 의존성을 맞춰야 한다.

```python
import pandas as pd
from evidently import Dataset, DataDefinition, Report
from evidently.presets import DataDriftPreset

schema = DataDefinition(numerical_columns=["purchase_count_30d"])
reference = Dataset.from_pandas(
    pd.DataFrame({"purchase_count_30d": list(range(20)) * 10}),
    data_definition=schema,
)
current = Dataset.from_pandas(
    pd.DataFrame({"purchase_count_30d": list(range(10, 30)) * 10}),
    data_definition=schema,
)
result = Report([DataDriftPreset()]).run(
    current_data=current, reference_data=reference
)
result.save_html("bookway-drift.html")
```

이는 통계 경로를 설명하는 데이터이며 실제 고객 분포나 경고 발생 결과가 아니다. 운영에서는 release, 시간 범위, 표본 수, reference 지문을 보고서와 같이 저장한다. 보고서를 만드는 작업 자체가 실패하면 “drift 없음”이 아니라 관측 실패이다.

## 경고 이후의 조사

구매 급증은 이벤트 중복, 집계 창, 프로모션, 고객 구성을 조사한다. 정답이 모이면 노출, 실험 배정을 맞춰 구간별 품질을 비교한다.

재학습은 정상 원천에서 성능 저하가 확인되었을 때의 선택이다. schema 오류는 변환 복구, 잘못 배포한 모델은 rollback, 새로운 고객 구간은 데이터, 기준선 재설계가 먼저일 수 있다.

LLMOps에서도 길이, 언어, retrieval score의 변화는 신호일 뿐이다. 답변의 근거성은 [DeepEval](/docs/tech/ops/llmops/deepeval/), [Ragas](/docs/tech/ops/llmops/ragas/) 등과 사람의 검토로 분리한다.

[공식 데이터, ML 검사](https://docs.evidentlyai.com/quickstart_ml) / [운영 알림 연결](/docs/tech/ops/mlops/monitoring/) / [기존 관측 실습](/docs/tech/ops/mlops/labs/ml-platform-labs-05-serving-monitoring/)
