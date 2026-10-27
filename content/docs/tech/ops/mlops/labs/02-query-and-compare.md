---
title: "02. 실행 비교와 메트릭 및 아티팩트 조회"
description: "실행 비교 기준을 고정하고 메트릭 이력과 모델 파일을 조회한다."
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 20
tags: ["mlflow", "mlops", "azure-machine-learning"]
aliases:
  - "/docs/tech/mlflow-azure-machine-learning/02-query-and-compare/"
---

화면에서 실행을 고르는 것과 같은 기준으로 재선택하는 것은 다르다. 01편의 기록을 코드로 비교하고 선택한 run의 지표와 파일을 읽는다.

## 준비 조건

[01편](/docs/tech/ops/mlops/labs/01-local-tracking/)의 파일과 학습 run이 필요하다. 같은 `mlflow-aml-lab` 폴더에서 실행한다. 새 PowerShell 창을 열었다면 로컬 기록 대상을 다시 지정한다.

```powershell
$env:MLFLOW_TRACKING_URI = "sqlite:///mlflow.db"
$env:MLFLOW_REGISTRY_URI = $env:MLFLOW_TRACKING_URI
$env:MLFLOW_EXPERIMENT_NAME = "mlflow-wine-study"
```

## 실행 비교와 선택 기록

UI 선택을 재현할 수 있도록 비교 기준을 코드로 남긴다.

### 비교 대상과 정렬 기준

`compare.py`:

```python
import json
from pathlib import Path

import mlflow


experiment = mlflow.get_experiment_by_name("mlflow-wine-study")
if experiment is None:
    raise RuntimeError("Experiment not found in the current tracking backend")

runs = mlflow.search_runs(
    experiment_ids=[experiment.experiment_id],
    filter_string="tags.study = 'mlflow-aml'",
    max_results=1000,
)
if runs.empty:
    raise RuntimeError("No study runs found")

completed = runs.loc[runs["status"].str.upper().eq("FINISHED")].copy()
if completed.empty:
    raise RuntimeError("No completed runs found")

for key in ["params.dataset_sha256", "params.split_seed"]:
    if completed[key].nunique(dropna=False) != 1:
        raise RuntimeError(f"Runs have different comparison conditions: {key}")

ranked = completed.sort_values(
    ["metrics.validation_accuracy", "metrics.validation_log_loss"],
    ascending=[False, True],
)
columns = [
    "run_id", "params.C", "metrics.validation_accuracy",
    "metrics.validation_log_loss",
]
print(ranked[columns].to_string(index=False))

selected = {
    "tracking_uri": mlflow.get_tracking_uri(),
    "run_id": str(ranked.iloc[0]["run_id"]),
}
Path("selected-run.json").write_text(
    json.dumps(selected, indent=2), encoding="utf-8"
)
print("Selection written to selected-run.json")
```

```powershell
.\.venv\Scripts\python.exe .\compare.py
```

고정 환경의 로컬 실행 결과다. 수치는 이 데이터의 한 번의 분할 결과이며 다른 데이터의 성능 목표가 아니다.

| C | 검증 정확도 | 검증 log loss |
| --- | --- | --- |
| 0.01 | 0.972222 | 0.479026 |
| 0.1 | 0.972222 | 0.182284 |
| 1.0 | 1.000000 | 0.081011 |

`C=1.0`을 선택한다. `C=0.01`과 `0.1`의 정확도는 같지만 log loss는 다르므로 정확도만으로 확률 품질을 판단할 수 없다.

조회는 조건에 맞는 최대 1,000개 run을 비교한다. 학습 코드나 평가 방식이 달라지면 experiment나 tag로 범위를 분리한다.

조회 결과를 DataFrame에서 정렬한다. [AML 실행 조회 문서](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-track-experiments-mlflow?view=azureml-api-2#order-runs)에 따르면 서버 `order_by`는 `metrics.*` 정렬을 지원하지 않는다. 로컬 문법이 원격에서도 같다고 가정하지 않는다.

`selected-run.json`에 run ID와 Tracking URI를 함께 저장해 다른 저장소의 동명 experiment와 구분한다.

### 마지막 메트릭과 전체 기록

`get_run()`과 `search_runs()`의 메트릭에는 이름별 마지막 기록 값이 들어간다. 같은 이름으로 여러 step을 남긴 학습 곡선 전체를 보려면 `MlflowClient.get_metric_history()`를 사용한다.

아티팩트도 run 객체 안에 파일 내용이 들어 있는 것은 아니다. 목록 조회와 실제 다운로드를 구분한다. 다음 코드는 앞의 비교 단계에서 선택한 run을 대상으로 기록과 모델 폴더를 확인한다.

`inspect_run.py`:

```python
import json
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient


selection = json.loads(
    Path("selected-run.json").read_text(encoding="utf-8")
)
if selection["tracking_uri"] != mlflow.get_tracking_uri():
    raise RuntimeError("Tracking backend changed; run compare.py again")

run_id = selection["run_id"]
client = MlflowClient()
run = client.get_run(run_id)
print("parameters:", run.data.params)
print("latest metrics:", run.data.metrics)

for point in client.get_metric_history(run_id, "validation_accuracy"):
    print("metric history:", point.step, point.value)

for artifact in client.list_artifacts(run_id):
    print("artifact:", artifact.path, "directory:", artifact.is_dir)

model_path = mlflow.artifacts.download_artifacts(
    run_id=run_id,
    artifact_path="model",
)
print("downloaded model folder:", model_path)
```

```powershell
.\.venv\Scripts\python.exe .\inspect_run.py
```

검증 정확도는 한 번 기록해 이력도 한 점이다. epoch별 기록을 추가하면 같은 API로 여러 step을 조회할 수 있다. 다운로드 폴더의 `MLmodel`과 환경 파일은 03편의 모델 계약과 연결된다.

### 조회와 기록을 확장할 때의 조건

| 확장 | 확인할 조건 |
| --- | --- |
| 조회 필터 | AML 지원 표에 맞춰 metric, parameter, tag와 비교 연산자 사용 |
| 복합 필터 | `AND`와 달리 `OR`는 지원하지 않으므로 같은 문법으로 기대하지 않음 |
| 하위 run | `mlflow.parentRunId` tag로 부모와 자식 실행을 연결해 조회 |
| 많은 메트릭 기록 | 개별 동기 호출의 반복과 배치 기록 또는 비동기 기록을 비교 |
| 비동기 기록 직후 조회 | 호출 반환과 저장 완료가 같지 않으므로 필요 시 반환된 작업의 `wait()` 사용 |

소수 메트릭만 기록하므로 동기 방식을 쓴다. 비동기 기록과 nested run은 선택 확장이지 AML 연결의 필수 조건이 아니다.

## 확인할 결과

`compare.py`는 비교 표와 `selected-run.json`을 만들고 예제에서는 `C=1.0`을 선택한다. `inspect_run.py`는 run 설정, 마지막 메트릭, 이력, 아티팩트 경로를 출력하며 모델 폴더는 다음 편에서 확인한다.

## 오류 확인

| 증상 | 확인할 부분 |
| --- | --- |
| Experiment를 찾지 못함 | 01편의 실행 여부, 작업 폴더와 Tracking URI |
| 완료된 run이 없음 | 실패한 학습의 원인을 먼저 조사 |
| 비교 조건이 다르다는 오류 | 데이터 지문이나 분할 시드가 다른 실행이 섞였는지 |
| 메트릭 이력이 한 점만 나옴 | 이번 코드는 정확도를 한 번 기록하며 step별 학습 곡선을 만들지 않음 |
| 선택 파일의 추적 대상 오류 | 현재 대상에서 `compare.py`를 다시 실행했는지 |

## 생각할 점

데이터 지문은 표의 데이터 식별자일 뿐 이용 권한이나 수집 시점을 설명하지 않는다. 실제 데이터에는 저장 위치, 스냅샷, 사용 범위, 라벨 정의도 기록한다.

- 점수 차이를 모델 설정의 차이로 설명하려면 어떤 조건이 같아야 하는가.
- 마지막 메트릭 값과 전체 이력은 각각 어떤 질문에 답하는가.
- 비교할 실행 수가 늘면 experiment와 tag의 범위를 어떻게 나눌 것인가.

## 참고 자료

- [실험과 실행 조회 및 비교](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-track-experiments-mlflow?view=azureml-api-2)
- [메트릭과 파일 기록](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-view-metrics?view=azureml-api-2)

[이전: 01. MLflow 기본과 로컬 실험 기록](/docs/tech/ops/mlops/labs/01-local-tracking/), [시리즈 목차](/docs/tech/ops/mlops/labs/), [다음: 03. 모델 형식과 재사용](/docs/tech/ops/mlops/labs/03-model-format-and-loading/)
