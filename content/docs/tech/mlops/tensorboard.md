---
title: "TensorBoard: 학습 과정의 이상을 읽기"
description: "Bookway 순위 모델의 step별 곡선을 실험, 데이터 버전과 연결"
date: 2026-10-25T08:43:00+09:00
weight: 25
tags: ["mlops", "tensorboard", "training"]
---

최종 성적만 보면 어느 과정에서 막혔는지 알기 어렵습니다. TensorBoard는 학습 중의 손실, 검증 지표, 계산 그래프 등을 시간과 step 축으로 보는 도구입니다. MLflow의 실험, 모델 출처와 겹치는 기능이 있지만, **학습 내부를 자세히 진단하는 화면**으로 역할을 정리할 수 있습니다.

## Bookway의 기록 단위

신경망 순위 모델을 사용하는 경우 train loss와 validation NDCG를 기록합니다. 인기 기준선이나 단순 SVD의 모든 실험에 TensorBoard가 필요한 것은 아닙니다. 모델 구조와 학습 라이브러리에 맞춰 선택합니다.

```text
events-20261024 + 시간 분할 + 설정
  → KFP 학습 작업
  → runs/학습실행ID의 event 파일
  → TensorBoard
  → MLflow run의 설정, 모델, 평가와 연결
```

여러 실행을 같은 디렉터리에 섞지 않습니다. global step은 재시작, 재개에서 중복되거나 초기화될 수 있으므로 checkpoint와 step 복원 정책도 정합니다.

## event 파일을 보는 순서

기존 학습이 `runs` 아래에 event 파일을 기록했다는 전제에서 로컬 UI를 실행합니다.

```powershell
tensorboard --logdir runs --host 127.0.0.1 --port 6006
```

학습 코드에는 사용하는 프레임워크의 SummaryWriter나 callback으로 스칼라를 기록합니다. `train/loss`, `validation/ndcg_at_10`, 학습률을 같은 step 기준으로 두면 손실 변화와 설정 변화의 관계를 볼 수 있습니다. histogram을 너무 자주 기록하면 I/O와 저장 비용이 커집니다.

| 곡선 | 가능한 원인 | 다음 조사 |
| --- | --- | --- |
| train 개선, validation 악화 | 과적합, 분할 차이 | 시간 분할, 정규화, 조기 종료 |
| loss가 갑자기 NaN | 잘못된 입력, 수치 불안정 | batch, dtype, 학습률 |
| 지표가 재시작 후 튐 | optimizer/step 복원 누락 | checkpoint 계약 |
| 모든 지표가 비정상적으로 높음 | 누수, 평가 오류 | 미래 이벤트, 후보 생성 |

그래프를 부드럽게 하는 smoothing은 원자료를 바꾸지는 않지만 급격한 실패를 가릴 수 있습니다. 원래 값과 함께 판단하고 최종 holdout 평가는 별도로 남깁니다.

## 보존과 운영의 경계

event 파일은 결과를 다시 학습할 수 있는 checkpoint가 아닙니다. optimizer, 모델, 난수 상태와 데이터 순서가 별도 필요합니다. event, 모델, MLflow run을 같은 실행 ID로 연결하되, 추천 API의 고객별 응답 로그를 TensorBoard에 기록하지 않습니다.

공유 UI는 인증된 내부 경로에 두고 이미지, 텍스트 summary에 원천 개인정보가 섞이지 않게 합니다. 프로덕션 요청 지연과 알림은 [Prometheus/Grafana](../monitoring/)의 책임입니다.

[공식 TensorBoard 소개](https://www.tensorflow.org/tensorboard/get_started) / [실험 출처 관리](../mlflow/) / [학습 실행 구조](../kubeflow/)
