---
title: 02. MLOps란 무엇인가
description: 닫힌 ML 생애주기, DevOps와의 차이, 자동화 수준으로 보는 MLOps 성숙도
date: 2026-10-21T07:33:00
lastmod: 2026-11-08T19:00:00+09:00
tags:
  - book-club
  - ml-platform-engineering
  - mlops
  - devops
weight: 20
math: false
draft: false
---
예측이 나빠지면 재학습부터 떠올리기 쉽다. 그런데 수집 과정이 깨졌거나 서버가 느려진 것이라면 고칠 곳이 따로 있다. 2장은 MLOps를 관측한 문제를 알맞은 다음 행동으로 연결하는 반복으로 설명하고, 그 반복을 얼마나 자동화했는지로 성숙도를 나눈다.

## 생애주기는 관측에서 다시 시작된다

MLOps 생애주기는 데이터 수집과 탐색적 데이터 분석(EDA), 모델링과 학습, 평가, 배포, 모니터링을 거쳐 유지와 개선으로 돌아온다.

![데이터 수집과 분석, 모델 학습과 평가, 배포와 모니터링을 반복하고 필요에 따라 모델을 폐기하는 ML 생애주기.](/images/image.png)

그림 2.2. 순환하는 ML 생애주기. 출처: Machine Learning Platform Engineering, 2장.

돌아갈 곳은 원인마다 다르다. 입력 스키마가 깨졌다면 수집을, 평가 기준이 잘못됐다면 문제 정의를, 서버가 느리면 서빙 구성을 고친다. 문제의 가치가 사라졌다면 모델을 폐기하는 것도 생애주기의 한 단계다.

앞 단계의 기록이 있어야 이 판단이 가능하다. 라벨 기준이 다르면 같은 사진에 정답이 둘 생기고, 평점이 없는 영화를 싫어한다고 읽을 수도 없다. EDA에서 세운 "평점은 허용 범위 안에 있다" 같은 가정은 실행 가능한 품질 검사로 옮긴다. 모델은 데이터에 코드와 설정을 적용한 산출물이므로 데이터 버전, 코드, 하이퍼파라미터, 평가셋을 실행 결과와 묶어 두어야 점수 차이의 원인을 가릴 수 있다. 배포한 뒤에는 모델 파일이 올라갔는지보다 같은 입력에 기대한 출력이 나오는지를 확인한다.

## 지표는 실패 비용에 맞춰 고른다

메일 10,000개 중 스팸이 100개라면 전부 통과시켜도 정확도는 99%다. 정확도 하나로 배포를 정할 수 없는 이유다.

| 실제 데이터 | 스팸으로 차단 | 정상으로 통과 |
| --- | --- | --- |
| 스팸 100개 | 80개 | 20개 |
| 정상 메일 9,900개 | 40개 | 9,860개 |

차단한 120개 중 스팸은 80개라 precision은 약 66.7%이고, 스팸 100개 중 80개를 잡았으니 recall은 80%다. 정상 메일을 막은 40건(FP)과 스팸을 놓친 20건(FN)의 비용은 같지 않다. 가상으로 FP를 건당 100, FN을 건당 2로 두면 손실을 비교할 수 있다.

```python
def error_cost(false_positive, false_negative, fp_cost=100, fn_cost=2):
    counts = (false_positive, false_negative)
    if any(not isinstance(value, int) or value < 0 for value in counts):
        raise ValueError("Error counts must be non-negative integers")
    return false_positive * fp_cost + false_negative * fn_cost


print(error_cost(40, 20))
print(error_cost(10, 50))
```

FP 40, FN 20이면 손실은 4,040이고, 임계값을 바꿔 FP 10, FN 50이 되면 1,100으로 준다. Recall은 떨어졌지만 이 가정에서는 두 번째가 낫고, 비용 비율을 뒤집으면 우열도 뒤집힌다. ROC-AUC는 순위를 가르는 능력의 요약이라 실제 임계값에서의 손실을 대신하지 못한다. 임계값은 검증 데이터에서 고르고, 최종 테스트 결과를 보면서 다시 조정하지 않는다. 전체 평균과 함께 중요한 집단별 결과와 표본 수도 본다.

## 모니터링 신호는 원인을 가리키는 단서다

운영에서는 정답이 늦게 도착하는 일이 많다. 오류와 지연은 바로 보이지만 예측이 맞았는지는 나중에야 안다. 그래서 바로 볼 수 있는 대리 신호와 정답이 들어온 뒤에 보는 실제 품질 지표를 나눠 두고, 예측 시점에 요청 식별자와 모델 버전을 남겨 늦게 온 정답과 잇는다. 이 연결이 없으면 어느 버전이 틀렸는지 집계할 수 없다.

데이터 드리프트는 입력 분포 `P(X)`가 바뀌는 것이고, 개념 드리프트는 입력과 정답의 관계 `P(Y|X)`가 바뀌는 것이다. 사용자 구성만 바뀌고 집단별 구매 방식이 그대로라면 데이터 드리프트에 가깝고, 같은 조건에서 구매 방식이 달라졌다면 개념 드리프트다. confidence나 드리프트 지표는 조사를 시작할 신호이지 정확도를 증명하지 않는다.

신호를 보고 곧장 재학습하면 위험하다. 특정 수집기에서 결측이 치솟았는데 재학습하면 장애 데이터를 새로운 정상으로 배우게 된다. API만 느려지고 같은 입력의 예측이 그대로라면 원인은 자원이나 피처 조회, 모델 로딩 쪽이다. 알림을 받을 사람과 그다음 행동이 정해져 있어야 대시보드가 쓸모를 가진다.

## DevOps에 데이터와 모델이라는 변경 원인이 더해진다

DevOps도 변경, 자동화, 모니터링, 협업을 다룬다. MLOps는 데이터와 모델이 코드와 따로 바뀐다는 조건을 더한다. 검증에는 통계적 품질과 데이터 누수, 집단별 성능이, 배포 단위에는 모델과 전처리, 피처 정의, 학습 파이프라인이, 관측에는 입력 분포와 예측 품질이 추가된다.

Google Cloud의 MLOps 아키텍처 문서는 CI와 CD에 CT(continuous training)를 더해 설명한다. CI는 코드 변경을 통합하고 검사하며, CD는 검증된 변경을 전달하거나 배포하고, CT는 새 데이터나 일정에 따라 모델을 다시 학습한다. CD는 언제든 내보낼 수 있게 준비해 두는 delivery와 자동으로 출시하는 deployment 두 뜻으로 쓰이므로, 승인이 어디에 끼어드는지 적어 둬야 한다. 실행을 자동화해도 잘못된 데이터나 품질이 떨어지는 후보는 출시 전에 걸러져야 한다.

노트북 하나에서 성공한 결과 뒤에는 데이터 처리, 환경, 모델, 서비스 사이의 의존성이 숨어 있다. 모델과 팀이 늘수록 수동 전달과 중복 구현이 변경 속도와 신뢰성을 깎는다. 성숙한 조직은 실험 기록과 모델 등록, 검증된 실행 경로를 공통 기능으로 제공해 배포할 때마다 절차를 새로 협의하지 않게 한다. 다만 아무도 쓰지 않는 표준은 공통 기능이 되지 못한다.

## 성숙도는 무엇을 반복 가능하게 했는지로 나뉜다

책은 Google이 나눈 세 자동화 수준을 소개한다.

| 수준 | 중심 특징 | 반복 가능해진 것 |
| --- | --- | --- |
| Level 0 | 사람이 스크립트와 파일을 넘기며 학습과 배포 | 없음, 담당자에게 의존 |
| Level 1 | 데이터, 모델 검증을 포함한 학습 파이프라인 자동화 | 새 데이터로 모델을 다시 만드는 과정 |
| Level 2 | 파이프라인 구성 요소 자체의 CI/CD | 학습 절차를 고쳐 배포하는 과정 |

매주 같은 전처리와 평가로 재학습이 돌아도 전처리 코드를 고칠 때마다 파일을 손으로 옮긴다면 Level 1에 머문다. API의 Docker 이미지만 자동 배포하는 것도 Level 2가 아니다. 재학습이 자주 돈다고 성숙한 것도 아니다. Level 1의 조건은 잘못된 데이터나 기존보다 나쁜 후보에서 실행이 멈추는 것이고, 아래 함수가 그런 검증 게이트를 흉내 낸다.

```python
def release_decision(report):
    required = {
        "missing_rate", "validation_auc", "baseline_auc",
        "p95_latency_ms", "schema_valid"
    }
    if not required.issubset(report):
        raise ValueError("Incomplete evaluation report")
    numeric = ("missing_rate", "validation_auc", "baseline_auc", "p95_latency_ms")
    from math import isfinite
    if any(
        isinstance(report[key], bool)
        or not isinstance(report[key], (int, float))
        or not isfinite(report[key])
        for key in numeric
    ):
        raise ValueError("Metrics must be finite numbers")
    if any(not 0 <= report[key] <= 1 for key in numeric[:3]):
        raise ValueError("Rates and AUC must be between 0 and 1")
    if report["p95_latency_ms"] < 0 or not isinstance(report["schema_valid"], bool):
        raise ValueError("Invalid latency or schema result")
    reasons = []
    if not report["schema_valid"]:
        reasons.append("schema mismatch")
    if report["missing_rate"] > 0.01:
        reasons.append("missing rate exceeds 1%")
    if report["validation_auc"] < report["baseline_auc"] + 0.02:
        reasons.append("validation AUC improvement is below 0.02")
    if report["p95_latency_ms"] > 200:
        reasons.append("p95 latency exceeds 200 ms")
    return {"eligible": not reasons, "reasons": reasons}


candidate = {
    "missing_rate": 0.005,
    "validation_auc": 0.84,
    "baseline_auc": 0.80,
    "p95_latency_ms": 170,
    "schema_valid": True,
}
print(release_decision(candidate))
print(release_decision({**candidate, "missing_rate": 0.08}))
```

결측률만 8%로 바꿔도 후보는 이유와 함께 거절된다. AUC가 높아도 입력 품질이나 지연 조건이 면제되지 않고, NaN처럼 비교를 빠져나가는 값은 오류로 처리한다. 게이트 통과는 검사 조건을 넘었다는 뜻이지 출시 완료가 아니며, 승인과 롤백 준비는 따로 필요하다.

## 정리

성숙도는 다음에 손볼 곳을 찾는 기준이고, 모든 조직이 같은 속도로 올라야 하는 서열은 아니다. 같은 조직 안에서도 모델마다 수준이 다르니 데이터 검증, 학습, 평가, 출시, 운영 대응을 하나씩 진단하고 변경 빈도에 맞춰 투자한다. 자동화 범위보다 잘못된 입력과 변경을 거절하고 원인에 맞게 복구하는 능력이 중요하며, 3장은 이 반복을 올릴 실행 기반으로 Kubernetes를 준비한다.

[이전: 01. 시작하기](../01-getting-started/), [시리즈 목차](../), [다음: 03. Kubernetes 기반](../03-kubernetes-foundation/)
