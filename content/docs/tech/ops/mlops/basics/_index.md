---
title: "도구 기초 가이드"
description: "MLflow, Feast, Kubeflow Pipelines, BentoML의 설치와 실무 활용 가이드"
date: 2026-10-25T19:30:00+09:00
weight: 1
tags: ["mlops", "mlflow", "feast", "kubeflow", "bentoml", "hands-on"]
sidebar:
  open: false
---

MLOps에서 함께 쓰는 MLflow, Feast, Kubeflow Pipelines, BentoML을 설치하고 기본 사용법부터 중급 설정까지 실행 순서대로 익힌다.

| 도구 | 맡는 일 | 가이드 |
| --- | --- | --- |
| MLflow | 실험 기록, 모델 저장과 버전, 레지스트리, 간단한 서빙 | [MLflow 기초](mlflow/) |
| Feast | 피처 정의, 과거 시점 조회, 온라인 저장소와 서빙 | [Feast 기초](feast/) |
| Kubeflow Pipelines | 컨테이너 작업의 순서와 아티팩트 전달, 실행 기록 | [Kubeflow Pipelines 기초](kubeflow-pipelines/) |
| BentoML | 모델을 API 서비스로 만들고 패키징, 컨테이너화 | [BentoML 기초](bentoml/) |

```mermaid
flowchart LR
    accTitle: 네 도구가 이어지는 위치
    accDescr: Feast가 학습용 과거 피처를 제공하고 학습 코드는 결과를 MLflow에 기록한다. Kubeflow Pipelines가 이 작업들을 순서대로 실행하며, BentoML 서비스는 MLflow의 고정 모델 버전과 Feast 온라인 피처로 요청에 응답한다.
    F["Feast<br/>피처 정의와 조회"] -->|"과거 시점 피처"| T["학습 코드"]
    T -->|"run, 모델 버전"| M["MLflow<br/>기록과 레지스트리"]
    K["Kubeflow Pipelines<br/>작업 순서와 아티팩트"] -.->|"실행"| T
    M -->|"고정 버전"| B["BentoML<br/>추론 서비스"]
    F -->|"온라인 피처"| B
```

네 도구는 서로를 직접 알지 못한다. Feast는 어떤 모델이 피처를 쓰는지 모르고, MLflow는 어떤 피처 정의로 학습했는지 스스로 기록하지 않는다. 둘을 잇는 것은 학습 코드와 그 코드가 남기는 기록이다. 가이드마다 이 연결 지점을 따로 짚었다.

순서는 MLflow, Feast, Kubeflow Pipelines, BentoML을 권한다. 각 가이드는 독립적으로 따라 할 수 있도록 별도 작업 폴더와 고정 버전을 사용한다. 명령은 Linux, macOS 또는 Windows의 WSL2를 기준으로 한다.

기초를 익힌 다음에는 [책 4~5장 로컬 실습 SOP](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/#book-lab-sop)에서 MLflow, Feast, Kubeflow Pipelines를 책의 코드 그대로 한 클러스터에서 이어 보고, [MLOps 실습](/docs/tech/ops/mlops/labs/)에서 Azure ML 연결과 여러 도구를 묶은 프로젝트를, [MLOps 설계 가이드](/docs/tech/ops/mlops/)에서 가상 서점 Bookway의 운영 요구사항을 기준으로 한 도구 배치를 볼 수 있다.

{{< section-list >}}
