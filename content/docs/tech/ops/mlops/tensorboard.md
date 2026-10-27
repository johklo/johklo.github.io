---
title: "TensorBoard: 학습 과정의 이상을 읽기"
description: "Bookway 순위 모델의 step별 곡선을 실험, 데이터 버전과 연결"
date: 2026-10-25T08:43:00+09:00
weight: 25
tags: ["mlops", "tensorboard", "training"]
aliases:
  - "/docs/tech/mlops/tensorboard/"
---

TensorBoard는 손실, 검증 지표, 계산 그래프를 step별로 보여 주는 **학습 내부 진단 도구**다. MLflow는 실험과 모델 출처를 관리한다.

## Bookway의 기록 단위

신경망 순위 모델은 train loss와 validation NDCG를 기록할 수 있다. 인기 기준선이나 단순 SVD에는 항상 필요하지 않으며 모델, 라이브러리로 선택한다.

```text
events-20261024 + 시간 분할 + 설정
  → KFP 학습 작업
  → runs/학습실행ID의 event 파일
  → TensorBoard
  → MLflow run의 설정, 모델, 평가와 연결
```

실행별 디렉터리를 쓰고 재시작, 재개 시 global step 중복이나 초기화를 다룰 checkpoint 복원 정책을 정한다.

## event 파일을 보는 순서

기존 학습이 `runs` 아래에 event 파일을 기록했다는 전제에서 로컬 UI를 실행한다.

```powershell
tensorboard --logdir runs --host 127.0.0.1 --port 6006
```

SummaryWriter나 callback으로 `train/loss`, `validation/ndcg_at_10`, 학습률을 같은 step에 기록한다. 잦은 histogram은 I/O, 저장 비용을 높인다.

| 곡선 | 가능한 원인 | 다음 조사 |
| --- | --- | --- |
| train 개선, validation 악화 | 과적합, 분할 차이 | 시간 분할, 정규화, 조기 종료 |
| loss가 갑자기 NaN | 잘못된 입력, 수치 불안정 | batch, dtype, 학습률 |
| 지표가 재시작 후 튐 | optimizer/step 복원 누락 | checkpoint 계약 |
| 모든 지표가 비정상적으로 높음 | 누수, 평가 오류 | 미래 이벤트, 후보 생성 |

smoothing은 원자료를 바꾸지 않지만 급격한 실패를 가릴 수 있으므로 원값과 함께 보고 최종 holdout을 별도 기록한다.

## 보존과 운영의 경계

event 파일은 checkpoint가 아니다. optimizer, 모델, 난수 상태, 데이터 순서를 별도 보존하고 event, 모델, MLflow run을 실행 ID로 연결한다. 고객 응답은 기록하지 않는다.

공유 UI는 인증된 내부 경로에 두고 이미지, 텍스트 summary에 원천 개인정보가 섞이지 않게 한다. 프로덕션 요청 지연과 알림은 [Prometheus/Grafana](/docs/tech/ops/mlops/monitoring/)의 책임이다.

[공식 TensorBoard 소개](https://www.tensorflow.org/tensorboard/get_started) / [실험 출처 관리](/docs/tech/ops/mlops/mlflow/) / [학습 실행 구조](/docs/tech/ops/mlops/kubeflow/)
