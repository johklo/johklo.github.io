---
title: "ML 플랫폼 실습 03. 같은 사용자 피처를 과거와 현재에서 조회하기"
description: "03. 같은 사용자 피처를 과거와 현재에서 조회하기 실행 절차, 결과 확인과 실패 실험"
date: 2026-10-24T15:00:00+09:00
lastmod: 2026-10-24T15:00:00+09:00
weight: 140
tags: ["ml-platform-labs", "mlops", "hands-on"]
aliases:
  - "/docs/tech/ml-platform-labs-03-feast/"
  - "/docs/tech/ml-platform-engineering-labs/ml-platform-labs-03-feast/"
---


과거 예측에 현재 평점 수를 쓰면 미래 정보 누수다. 피처 스토어는 값과 당시 이용 가능 시점을 다룬다.

영화 평점으로 사용자 평균과 건수를 계산한 뒤 Feast SDK로 등록, 과거 조회, materialization과 온라인 조회를 실행한다.

## 영화 데이터에서 피처 정의 만들기

[영화 추천 과정](/docs/tech/ops/mlops/labs/ml-platform-labs-01-movies/)의 `data/movies`가 필요하다. 없다면 먼저 `movies prepare`를 실행한다.

```powershell
uv run --extra feast ml-labs tools feast init --data data/movies --output integrations/feast
uv run --extra feast ml-labs tools feast run --repo integrations/feast --action apply
```

`feature_store.yaml`, `features.py`, 피처 Parquet와 메타데이터를 만든다. 기존 정의를 덮어쓰지 않으므로 재실행에는 새 출력 폴더를 쓴다.

학습 이벤트를 사용자별 시간순으로 누적해 `average_rating`, `ratings_count`를 만들고 검증, 테스트 평점은 제외한다.

SVD는 사용자 점수 행렬을 쓰므로 피처 조회로 가중치가 바뀌지 않는다. [통합 운영 과정](/docs/tech/ops/mlops/labs/ml-platform-labs-09-integrated-operations/)의 API는 Feast 평점 수와 관측 시점으로 추천을 분기하고 모델, 피처 지문, 누락과 최신성을 검사한다.

## 먼저 온라인 조회가 실패하는지 보기

```powershell
uv run --extra feast ml-labs tools feast run --repo integrations/feast --action online --user-id u007
```

materialization 전에는 오류가 나야 한다. 정의 등록 `apply`와 온라인 값 채우기는 별개이며 누락을 0이나 빈 정상 결과로 바꾸면 문제를 숨긴다.

## 과거 시점 조회

```powershell
uv run --extra feast ml-labs tools feast run --repo integrations/feast --action historical --user-id u007
```

기준 시점별로 조회해 첫 평점 전에는 값이 없고 이후에는 누적 건수가 늘어나는지 확인한다.

Feast 과거 조회가 시간 의미를 자동 해결하지는 않는다. 이 실습은 이벤트 즉시 사용을 가정하므로 실데이터의 수집 지연, 정정, backfill에는 이벤트 시점과 사용 가능 시점을 구분한다.

## 일부 시점까지만 온라인으로 채우기

```powershell
uv run --extra feast ml-labs tools feast run --repo integrations/feast --action materialize --end-date "2025-01-05T00:00:00+00:00"
uv run --extra feast ml-labs tools feast run --repo integrations/feast --action online --user-id u007
```

생성 이벤트는 2025년 1월 시작하며 기본 데이터의 `u007`은 해당 시점까지 5건이다. 데이터 변경 시 원천 이벤트와 대조한다.



```powershell
uv run --extra feast ml-labs tools feast run --repo integrations/feast --action materialize
uv run --extra feast ml-labs tools feast run --repo integrations/feast --action online --user-id u007
```

학습 평점 14건만 반영하며 검증, 테스트를 포함한 18건은 아니다.

온라인 저장소는 로컬 SQLite다. Redis 없는 흐름 확인용이며 운영 수준의 처리량, 지연 검증은 아니다.

## 피처 조회에 필요한 기록

| 대상 | 확인할 내용 |
| --- | --- |
| entity | 원천 데이터에 실제 존재하는 사용자 ID인지 |
| source | 어떤 학습 데이터와 지문에서 만들어졌는지 |
| event timestamp | 통계가 어느 시점까지의 이벤트를 포함하는지 |
| historical query | 조회 시점보다 뒤의 평점이 섞이지 않는지 |
| online query | materialization 범위와 조회값이 일치하는지 |

FeatureView TTL과 온라인 키 만료는 다르다. 최신성, 지연 이벤트와 누락 처리 정책을 정한다.

## 라우터와 순위 모델의 구분

평점 수 라우터는 [통합 운영 과정](/docs/tech/ops/mlops/labs/ml-platform-labs-09-integrated-operations/)에서 실행한다. 평균 평점, 장르 선호도를 쓰는 순위 모델은 제외했으며 연결하려면 피처 계약, 학습, 서빙 변환을 함께 바꿔야 한다.



[이전: 객체 탐지](/docs/tech/ops/mlops/labs/ml-platform-labs-02-cards/) / [다음: 파이프라인](/docs/tech/ops/mlops/labs/ml-platform-labs-04-pipelines/)


실행 코드는 [실습 저장소](https://github.com/johklo/ml-platform-engineering-labs)에서 내려받는다. [원본 가이드](https://github.com/johklo/ml-platform-engineering-labs/blob/main/docs/03-feast.md)
