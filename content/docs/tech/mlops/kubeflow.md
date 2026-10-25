---
title: "Kubeflow Pipelines: 학습과 피처 작업의 실행 경계"
description: "컴포넌트·아티팩트·캐시·재시도를 Bookway의 배치 출시 흐름에 적용"
date: 2026-10-25T08:43:00+09:00
weight: 40
tags: ["mlops", "kubeflow", "pipelines"]
---

Kubeflow Pipelines는 공장의 작업 지시서와 실행 기록에 가깝습니다. “정제 후 학습”이라는 순서뿐 아니라 **어느 이미지가 무엇을 읽고 무엇을 남기는지** 명시합니다. Kubeflow 전체와 KFP는 같지 않으며, 여기서는 독립 설치도 가능한 KFP를 다룹니다.

## Bookway의 DAG

| 컴포넌트 | 입력 | 출력 | 실패 조건 |
| --- | --- | --- | --- |
| 데이터 검사 | 스냅샷 URI·지문 | 검증 manifest | schema·중복·시간 경계 위반 |
| 피처 생성 | manifest·변환 버전 | offline 피처 URI | 미래 정보·누락률 초과 |
| 학습 | 피처 URI·설정 | MLflow run·후보 manifest | 학습 실패·산출물 없음 |
| 평가 | 후보·검증 집합 | 보고서·통과 여부 | 기준선 대비 저하·지연 초과 |
| 출시 요청 | 승인된 보고서 | 출시 후보 `rec-r17` | 지문 불일치·승인 없음 |

온라인 materialization은 모델 학습과 분리할 수 있습니다. 실시간 최신성 요구에 따라 별도 스케줄을 두되 모델의 피처 계약이 준비됐는지 출시 전에 확인합니다.

## 작은 SDK 예제

다음 코드는 v2 스타일 KFP SDK가 설치된 환경에서 **게이트 컴포넌트를 컴파일**하는 예제입니다. 학습·클러스터 실행까지 포함하지 않으며 점수는 앞 평가 작업의 입력을 받습니다.

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

실무에서는 검증·학습을 이 앞에 연결하고 출력 artifact의 `.path`나 `.uri` 계약을 맞춥니다. 한 Pod의 `C:\...`나 임시 경로를 다음 Pod에 넘기는 것은 공유가 아닙니다. object store와 service account를 구성해야 합니다. 운영 이미지는 위 예제의 가변 태그 대신 검증한 digest로 고정합니다.

## 캐시와 재시도

캐시는 같은 작업을 다시 하지 않는 데 유용하지만 원천이 같은 URI에서 바뀌면 이전 결과를 잘못 재사용할 수 있습니다. 데이터 지문·코드·설정·기준 시점을 명시 입력에 포함합니다. 현재 시간이나 외부 API에 의존하는 작업은 캐시 사용 여부를 별도로 정합니다.

읽기·학습은 재시도하기 쉬워도 Registry 등록·materialization·출시 포인터 변경은 부작용이 있습니다. `pipeline_run_id`와 업무 요청 ID를 나눠 결과가 이미 생성됐는지 조회하고, 중복 등록이 허용되는지 정책을 둡니다.

## 클러스터 운영

컴파일 성공은 Pod 실행이나 object store 접근 성공이 아닙니다. 제출 뒤에는 scheduling, 이미지 pull, 자원 부족, artifact 업로드와 종료 코드를 순서대로 봅니다. 실패한 학습을 빈 평가 보고서로 넘기지 않습니다.

팀별 namespace·quota·service account를 분리하고 GPU 학습과 CPU 전처리의 자원을 따로 정합니다. 실행 메타데이터와 모델 artifact가 다른 저장소에 있으므로 양쪽 보존 정책도 맞춰야 합니다.

[공식 KFP 개요](https://www.kubeflow.org/docs/components/pipelines/overview/) / [기존 클러스터 실행 기록](../../machine-learning-platform-engineering/05-ml-pipelines/) / [배포 경로와의 구분](../gitops/)
