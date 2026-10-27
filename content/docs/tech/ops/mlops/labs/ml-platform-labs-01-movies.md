---
title: "ML 플랫폼 실습 01. 영화 추천을 시간 순서대로 학습하고 평가하기"
description: "01. 영화 추천을 시간 순서대로 학습하고 평가하기 실행 절차, 결과 확인과 실패 실험"
date: 2026-10-24T15:00:00+09:00
lastmod: 2026-10-24T15:00:00+09:00
weight: 120
tags: ["ml-platform-labs", "mlops", "hands-on"]
aliases:
  - "/docs/tech/ml-platform-labs-01-movies/"
  - "/docs/tech/ml-platform-engineering-labs/ml-platform-labs-01-movies/"
---


미래 평점으로 학습하면 시험 답안을 미리 본 셈이다. 추천 데이터는 무작위 행이 아니라 정보가 알려진 시점으로 나눈다.

사용자별 과거 평점으로 학습하고 이후 데이터로 검증, 테스트한다. 합성 평점 생성에 쓴 숨은 취향 벡터는 모델에 공개하지 않는다.

## 작은 데이터로 전체 연결하기

```powershell
uv run ml-labs movies prepare --output data/movies
uv run ml-labs movies train --data data/movies --output .ml-labs/runs/movies --rank 4
uv run ml-labs movies evaluate --candidate .ml-labs/runs/movies/candidate.json --data data/movies --report .ml-labs/reports/movies.json --max-rmse 1.5
uv run ml-labs register --candidate .ml-labs/runs/movies/candidate.json --report .ml-labs/reports/movies.json --name movie-recommender
```

`ratings.csv`는 `user_id`, `item_id`, `rating`, `timestamp`, `split`을 포함하며 중복, 평점 범위와 사용자별 분할 시점을 검사한다.

`train`은 사용자 평균 대비 취향을 저차원 행렬로 근사하는 SVD를 쓴다. 본 영화는 제외하고 신규 사용자는 학습 평점의 영화 평균을 쓰지만, 노출 수와 신뢰도는 보정하지 않는다.

## 결과를 읽는 순서

`candidate.json`의 `validation_rmse`를 `baseline_rmse`와 비교한다. RMSE는 낮을수록 좋지만 `rank`가 높다고 개선되지는 않는다. 기본 게이트는 RMSE 상한이며 `--min-ndcg-lift`는 인기 기준선 대비 NDCG@5 개선 폭도 검사한다.

검증 통과 후 테스트에서 평점 4 이상 영화의 Recall@5를 계산한다. 관련 영화가 없으면 `null`을 기록한다.

낮은 평점 오차가 좋은 순위를 보장하지 않는다. rank 선택은 검증에서 하고 테스트는 최종 확인에만 쓴다.

## 실제 MovieLens로 교체하기

합성 데이터는 연결 확인용이다. 희소성과 인기 편향은 이용 조건에 따라 [MovieLens latest-small](https://grouplens.org/datasets/movielens/latest/) ZIP을 내려받아 확인한다. 자동 다운로드, 재배포는 하지 않는다.

```powershell
uv run ml-labs movies import-movielens --archive .\ml-latest-small.zip --output data/movielens
uv run ml-labs movies train --data data/movielens --output .ml-labs/runs/movielens --rank 16
uv run ml-labs movies evaluate --candidate .ml-labs/runs/movielens/candidate.json --data data/movielens --report .ml-labs/reports/movielens.json
```

가져오기는 사용자당 10건, 시점 3개 이상이 필요하다. 같은 타임스탬프는 같은 분할에 넣고 시점 그룹을 약 80, 10, 10%로 나눠 행 비율은 다를 수 있다.

MovieLens 0.5~5점은 `1 + (원래 평점 - 0.5) × 4 / 4.5`로 바꾸고 ZIP 지문과 변환식을 manifest에 기록한다. 4점 기준도 달라진다.

대상은 latest-small이다. 수천만 건은 조밀 행렬 구현의 메모리를 넘으므로 확장에는 희소 행렬, ANN, 후보 생성과 순위화 설계가 필요하다.

## 평가 게이트의 거절 경로

아주 낮은 RMSE 상한으로 기존 후보를 평가한다.

```powershell
uv run ml-labs movies evaluate --candidate .ml-labs/runs/movies/candidate.json --data data/movies --report .ml-labs/reports/movies-rejected.json --max-rmse 0.01
```

종료 코드는 0이 아니어야 하고 보고서에는 `passed: false`가 남아야 한다. 해당 보고서의 `register`도 거절되어야 경고가 아닌 게이트로 동작한다.

[서빙 과정](/docs/tech/ops/mlops/labs/ml-platform-labs-05-serving-monitoring/)에서 신규, 기존 사용자의 응답을 비교한다.

## 후보 비교와 추가 평가 범위

rank 2, 4, 8을 같은 데이터와 기준으로 비교한다. 학습은 인기 기준선과 모델의 검증 Recall@5, NDCG@5를 기록한다. [통합 운영 실험](/docs/tech/ops/mlops/labs/ml-platform-labs-09-integrated-operations/)은 검증 NDCG로 고른 후보만 테스트하며 장르 커버리지와 활동량 세그먼트는 평가 범위 밖이다.



[이전: 구조와 준비](/docs/tech/ops/mlops/labs/ml-platform-labs-00-foundation/) / [다음: 객체 탐지](/docs/tech/ops/mlops/labs/ml-platform-labs-02-cards/)


실행 코드는 [실습 저장소](https://github.com/johklo/ml-platform-engineering-labs)에서 내려받는다. [원본 가이드](https://github.com/johklo/ml-platform-engineering-labs/blob/main/docs/01-movies.md)
