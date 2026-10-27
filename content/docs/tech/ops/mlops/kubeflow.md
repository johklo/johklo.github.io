---
title: "Kubeflow Pipelines: 학습과 피처 작업의 실행 경계"
description: "컴포넌트, 아티팩트, 캐시, 재시도를 Bookway의 배치 출시 흐름에 적용"
date: 2026-10-25T08:43:00+09:00
weight: 40
tags: ["mlops", "kubeflow", "pipelines"]
aliases:
  - "/docs/tech/mlops/kubeflow/"
---

Kubeflow Pipelines(KFP)는 작업 순서와 **각 이미지의 입력, 출력**을 명시한다. Kubeflow 전체와 다르며 KFP만 설치할 수도 있다.

## Bookway의 DAG

| 컴포넌트 | 입력 | 출력 | 실패 조건 |
| --- | --- | --- | --- |
| 데이터 검사 | 스냅샷 URI, 지문 | 검증 manifest | schema, 중복, 시간 경계 위반 |
| 피처 생성 | manifest, 변환 버전 | offline 피처 URI | 미래 정보, 누락률 초과 |
| 학습 | 피처 URI, 설정 | MLflow run, 후보 manifest | 학습 실패, 산출물 없음 |
| 평가 | 후보, 검증 집합 | 보고서, 통과 여부 | 기준선 대비 저하, 지연 초과 |
| 출시 요청 | 승인된 보고서 | 출시 후보 `rec-r17` | 지문 불일치, 승인 없음 |

온라인 materialization은 별도 스케줄로 실행하고 출시 전에 모델 피처 계약을 확인한다.

## 작은 SDK 예제

다음은 v2 KFP SDK의 **게이트 컴포넌트 컴파일** 예제다. 학습, 클러스터 실행은 포함하지 않고 앞선 평가 점수를 받는다.

```python
from kfp import compiler, dsl

@dsl.component(base_image="python:3.12-slim")
def quality_gate(ndcg: float, baseline: float) -> str:
    import math
    if not all(math.isfinite(x) and 0 <= x <= 1 for x in (ndcg, baseline)):
        raise ValueError("Invalid NDCG")
    if ndcg < baseline:
        raise ValueError("Candidate is below baseline")
    return "eligible"

@dsl.pipeline(name="bookway-quality-gate")
def pipeline(ndcg: float, baseline: float):
    quality_gate(ndcg=ndcg, baseline=baseline)

compiler.Compiler().compile(
    pipeline_func=pipeline, package_path="bookway-gate.yaml"
)
```

검증, 학습을 앞에 연결하고 artifact `.path`, `.uri` 계약을 맞춘다. Pod 로컬 경로는 공유가 아니므로 object store와 service account를 구성하고 운영 이미지는 검증 digest로 고정한다.

## 캐시와 재시도

캐시는 같은 작업을 다시 하지 않는 데 유용하지만 원천이 같은 URI에서 바뀌면 이전 결과를 잘못 재사용할 수 있다. 데이터 지문, 코드, 설정, 기준 시점을 명시 입력에 포함한다. 현재 시간이나 외부 API에 의존하는 작업은 캐시 사용 여부를 별도로 정한다.

읽기, 학습과 달리 Registry 등록, materialization, 출시 변경은 부작용이 있다. `pipeline_run_id`와 업무 ID로 중복을 확인하고 재시도 정책을 정한다.

## 클러스터 운영

컴파일 성공은 Pod 실행이나 object store 접근 성공이 아니다. 제출 뒤에는 scheduling, 이미지 pull, 자원 부족, artifact 업로드와 종료 코드를 순서대로 본다. 실패한 학습을 빈 평가 보고서로 넘기지 않는다.

namespace, quota, service account를 분리하고 GPU 학습, CPU 전처리 자원을 따로 둔다. 메타데이터와 모델 artifact의 보존 정책도 맞춘다.

[공식 KFP 개요](https://www.kubeflow.org/docs/components/pipelines/overview/) / [기존 클러스터 실행 기록](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/) / [배포 경로와의 구분](/docs/tech/ops/mlops/gitops/)
