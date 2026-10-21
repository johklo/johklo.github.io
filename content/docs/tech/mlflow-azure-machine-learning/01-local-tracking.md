---
title: "01. MLflow 기본과 로컬 실험 기록"
description: "Experiment와 run을 구분하고 같은 학습 코드의 설정과 결과를 로컬에 기록하기"
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 10
tags: ["mlflow", "mlops", "azure-machine-learning"]
---

학습 코드를 실행할 때마다 설정과 결과를 같은 기준으로 남기는 것부터 시작했다. 이 편은 Azure 구독 없이 로컬 Python에서 MLflow를 익히는 단계다.

도구의 정의와 전체 MLOps에서의 위치는 [목차의 MLflow와 BentoML 설명](../#mlflow와-bentoml의-의미)에 두었다. 여기서는 MLflow의 실험 기록부터 실제 코드로 확인한다.

## 준비 조건과 이번 편의 결과

Python 3.11과 PowerShell을 사용한다. 새 실습 폴더를 만들고 아래 파일을 저장한다. 이 편을 마치면 서로 다른 `C`를 가진 세 개의 run, 검증 보고서와 모델 파일이 남아야 한다. AML 플러그인과 workspace는 아직 필요하지 않다.

## 실험 기록의 단위

| 개념 | 이 실습에서의 의미 | 예시 |
| --- | --- | --- |
| Experiment | 비교할 실행을 묶는 단위 | `mlflow-wine-study` |
| Run | 한 번의 학습과 기록 | `C=0.1`인 학습 한 번 |
| Parameter | 실행에 사용한 설정 | `C`, 분할 시드, 데이터 지문 |
| Metric | 실행 결과의 수치 | 검증 정확도, 검증 log loss |
| Artifact | 파일 형태의 결과 | 분류 보고서, 학습 코드 |
| MLflow Model | 모델과 입출력 및 환경 정보의 묶음 | `model` 경로의 Pipeline |
| Registered Model | 이름 아래 버전으로 관리할 모델 | `wine-logistic-study`의 특정 버전 |

Tracking URI는 기록을 보낼 대상을 가리킨다. 학습을 실행할 컴퓨터를 정하는 값은 아니다. 이 구분이 로컬 실습에서 AML로 넘어갈 때의 기준이다.

모델을 아티팩트로 올리는 것과 MLflow 모델로 기록하는 것도 다르다. `log_artifact()`는 파일을 올리고, `mlflow.sklearn.log_model()`은 모델 파일에 더해 `MLmodel`, 의존성, 입출력 signature 같은 정보를 묶는다.

## 실습 환경과 파일 구성

명령은 Windows PowerShell을 기준으로 적었다. 별도 실습 폴더에서 실행하며, Python 3.11이 설치되어 있다는 전제다. 가상환경 활성화 없이 해당 환경의 실행 파일을 직접 호출한다.

```powershell
New-Item -ItemType Directory -Path mlflow-aml-lab
Set-Location .\mlflow-aml-lab
py -3.11 -m venv .venv
New-Item -ItemType Directory -Path src
```

이 편에서 만드는 파일은 `requirements.txt`와 `src\train.py`다. 뒤의 편에서도 같은 폴더를 사용하며 필요한 파일을 추가한다.

```text
mlflow-aml-lab
  requirements.txt
  src
    train.py
```

### 패키지 버전

이 예제는 MLflow 전체의 최신 기능보다 AML 모델 연동 경로에 맞췄다. [공식 모델 로깅 문서](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-mlflow-models?view=azureml-api-2)는 현재 MLflow 2.16.x 이하를 사용하도록 명시하고 있어 `2.16.2`로 고정했다. MLflow 3.x의 예제를 섞지 않는다.

연결된 모델 변환 문서에는 `name=`을 사용하는 예시도 있다. 이 노트의 실행 코드는 2.16.2 기준의 `artifact_path=`로 통일했다. 서로 다른 문서의 예제를 가져올 때 호출 인자와 설치 버전을 함께 확인할 부분이다.

`requirements.txt`:

```text
mlflow==2.16.2
scikit-learn==1.5.1
pandas==2.2.3
numpy==1.26.4
sqlalchemy==2.0.43
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

SQLite 저장소에 사용하는 SQLAlchemy도 함께 고정했다. MLflow 버전만 고정해도 나머지 패키지의 새 버전이 설치되면서 실행이 달라질 수 있기 때문이다. 직접 지정하지 않은 의존성은 설치 시점에 결정되므로, 같은 조합으로 환경을 다시 만들려면 설치 후 `pip freeze` 결과도 보관한다.

```powershell
.\.venv\Scripts\python.exe -m pip freeze | Set-Content -Encoding utf8 .\requirements.local.lock.txt
```

이 버전 고정은 예제의 실행 기준이다. 공개 MLflow 서버 운영을 위한 보안 기준이나 최신 버전 권고를 뜻하지 않는다. 아래 UI는 로컬 루프백 주소에서만 사용한다.

원격 기록용 클라이언트만 필요하면 `mlflow-skinny`를 검토할 수 있다. 다만 SQLite 저장소, 로컬 서버와 UI를 포함하는 이번 실습에서는 전체 `mlflow` 패키지를 사용한다.

## 로컬에서 한 번의 학습 기록

### 데이터와 평가 기준

전체 데이터를 학습 60%, 검증 20%, 테스트 20% 비율로 나눈다. 표본 수는 분할 과정에서 정수로 조정된다. 시드와 분할 방식은 실행마다 같게 유지하고, `C`만 바꾼다.

`C`는 Logistic Regression의 규제 강도와 반대 방향으로 움직이는 값이다. 이 실습에서는 검증 정확도가 높은 후보를 고르고, 정확도가 같으면 검증 log loss가 낮은 후보를 고른다. 테스트 데이터는 후보 선택에 쓰지 않는다.

전처리인 `StandardScaler`와 분류기를 하나의 Pipeline으로 묶는다. 학습 데이터로만 전처리를 학습하고, 검증과 테스트에는 이미 학습한 변환을 적용하기 위해서다.

### 학습 코드

`src\train.py`:

```python
import argparse
import hashlib
import platform
from importlib.metadata import version
from time import perf_counter

import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from sklearn.datasets import load_wine
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, log_loss
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def load_data():
    dataset = load_wine(as_frame=True)
    fingerprint = hashlib.sha256(
        dataset.frame.to_csv(index=False).encode("utf-8")
    ).hexdigest()
    X_train, X_holdout, y_train, y_holdout = train_test_split(
        dataset.data,
        dataset.target,
        test_size=0.4,
        random_state=42,
        stratify=dataset.target,
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_holdout,
        y_holdout,
        test_size=0.5,
        random_state=42,
        stratify=y_holdout,
    )
    return X_train, X_val, X_test, y_train, y_val, y_test, fingerprint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--C", type=float, required=True)
    parser.add_argument("--autolog", action="store_true")
    args = parser.parse_args()
    if args.C <= 0:
        parser.error("--C must be greater than zero")

    X_train, X_val, _, y_train, y_val, _, fingerprint = load_data()
    model = Pipeline([
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(
            C=args.C, max_iter=1000, random_state=42
        )),
    ])

    if args.autolog:
        mlflow.sklearn.autolog(log_models=False, log_datasets=False)

    with mlflow.start_run() as run:
        mlflow.set_tags({
            "study": "mlflow-aml",
            "model_type": "scaled-logistic-regression",
        })
        mlflow.log_params({
            "C": args.C,
            "split_seed": 42,
            "dataset": "sklearn.load_wine",
            "dataset_sha256": fingerprint,
            "train_rows": len(X_train),
            "validation_rows": len(X_val),
        })

        started = perf_counter()
        model.fit(X_train, y_train)
        fit_seconds = perf_counter() - started
        predictions = model.predict(X_val)
        probabilities = model.predict_proba(X_val)
        mlflow.log_metrics({
            "validation_accuracy": accuracy_score(y_val, predictions),
            "validation_log_loss": log_loss(y_val, probabilities),
            "fit_seconds": fit_seconds,
        })
        mlflow.log_dict(
            classification_report(
                y_val, predictions, output_dict=True, zero_division=0
            ),
            "reports/validation.json",
        )
        mlflow.log_artifact(__file__, artifact_path="source")
        mlflow.log_dict(
            {
                "python": platform.python_version(),
                "packages": {
                    name: version(name)
                    for name in [
                        "mlflow", "scikit-learn", "pandas", "numpy",
                        "cloudpickle",
                    ]
                },
            },
            "environment.json",
        )
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            signature=infer_signature(X_train, model.predict(X_train)),
            input_example=X_train.head(3),
        )
        print(f"tracking_uri={mlflow.get_tracking_uri()}")
        print(f"run_id={run.info.run_id}")


if __name__ == "__main__":
    main()
```

Tracking URI와 experiment 이름을 학습 코드에 고정하지 않았다. 로컬에서는 환경 변수로 지정하고, AML Job에서는 서비스가 제공하는 실행 문맥을 사용한다.

`with mlflow.start_run()`은 실행의 시작과 종료를 묶는다. 예외가 발생하면 정상 완료와 구분된 실행 상태가 남는다. 실행 하나에서 `C`를 계속 덮어쓰는 대신 값마다 별도 run을 만든다.

### 세 번의 실행

모든 명령은 실습 폴더의 루트에서 실행한다. 상대 SQLite 경로를 사용하므로 작업 폴더가 바뀌면 다른 DB를 읽게 된다.

```powershell
$env:MLFLOW_TRACKING_URI = "sqlite:///mlflow.db"
$env:MLFLOW_REGISTRY_URI = $env:MLFLOW_TRACKING_URI
$env:MLFLOW_EXPERIMENT_NAME = "mlflow-wine-study"

foreach ($c in @("0.01", "0.1", "1.0")) {
    .\.venv\Scripts\python.exe .\src\train.py --C $c
    if ($LASTEXITCODE -ne 0) { throw "Training failed for C=$c" }
}
```

SQLite에는 실행 메타데이터가, 로컬 아티팩트 저장소에는 보고서와 모델 파일이 남는다. 이 예제의 기본 로컬 아티팩트 위치는 `mlruns`다. DB 파일만 복사하면 모델 파일까지 옮겨지는 것은 아니다.

### UI에서 확인할 항목

같은 폴더에서 별도 PowerShell 창을 열고 실행한다.

```powershell
.\.venv\Scripts\mlflow.exe ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5000
```

브라우저에서 `http://127.0.0.1:5000`을 연다. UI 종료는 해당 터미널의 `Ctrl+C`로 처리한다.

| 확인 위치 | 남아 있어야 할 내용 |
| --- | --- |
| Experiment | `mlflow-wine-study` 아래 세 번의 실행 |
| Parameters | 서로 다른 `C`, 같은 데이터 지문과 분할 시드 |
| Metrics | 검증 정확도, 검증 log loss, 학습 시간 |
| Artifacts | `reports/validation.json`, `source/train.py`, `environment.json` |
| Model | `model` 아래 `MLmodel`과 모델 파일 및 환경 정보 |

Signature는 모델이 기대하는 열과 타입을 설명한다. 입력 예시는 호출 형태를 확인하는 자료다. 두 정보가 데이터 품질이나 업무상 정확성까지 보장하지는 않는다.

### 기록 API를 고르는 기준

[메트릭과 파일 기록 문서](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-view-metrics?view=azureml-api-2)는 기록의 타입에 따라 API를 나눈다. 보고서를 출력한 것과 구조화된 메트릭으로 저장한 것은 다르다.

| 남길 정보 | 사용할 API | 이번 예제와의 연결 |
| --- | --- | --- |
| 실행 설정 | `log_param()`, `log_params()` | `C`, 분할 시드, 데이터 지문 |
| 숫자로 비교할 결과 | `log_metric()`, `log_metrics()` | 검증 정확도와 log loss |
| 단계별로 변하는 숫자 | `log_metric()`의 `step` | epoch별 손실 등을 기록할 때 확장 |
| JSON 또는 YAML 보고서 | `log_dict()` | 클래스별 검증 보고서 |
| 기존 파일 | `log_artifact()`, `log_artifacts()` | 학습 코드와 추가 결과 파일 |
| 이미지와 그래프 | `log_image()`, `log_figure()` | 혼동행렬이나 시각화로 확장 |
| 실행을 분류할 정보 | `set_tag()`, `set_tags()` | 이번 학습을 구분하는 `study` tag |

AML Job의 `print()` 출력은 진단 로그에서 볼 수 있지만 메트릭 차트의 값으로 자동 변환되지는 않는다. 코드의 오류나 진행 상황은 로그에, 실행 간 비교할 숫자는 MLflow 메트릭에 남기는 식으로 나누었다.

## Autologging을 더했을 때의 차이

수동 기록을 확인한 뒤 자동 기록을 더하는 순서로 잡았다.

```powershell
.\.venv\Scripts\python.exe .\src\train.py --C 0.1 --autolog
```

`--autolog`는 `mlflow.sklearn.autolog()`를 켠다. 이 예제에서는 모델의 자동 기록을 끄고, 같은 `log_model()`에서 signature와 입력 예시를 기록한다. 자동 기록과 수동 기록으로 같은 모델을 중복해서 남기지 않기 위해서다.

자동 기록으로 늘어나는 항목은 프레임워크와 버전에 따라 달라진다. 업무상 평가 기준, 데이터 이용 조건, 선택 이유까지 자동으로 기록되는 것은 아니다. 이 실습의 검증 메트릭과 데이터 지문은 수동으로 남긴다.

## 확인할 결과

처음 세 번의 실행과 `--autolog` 실행은 서로 다른 run이다. 자동 기록 예제까지 실행하면 run 수가 하나 더 늘어난다. 설정은 Parameters, 숫자는 Metrics, 보고서와 코드는 Artifacts에서 확인한다. 다음 편에서는 이 기록을 UI가 아닌 코드로 다시 조회한다.

## 오류 확인

| 증상 | 확인할 부분 |
| --- | --- |
| `mlflow`를 import하지 못함 | `.venv` 안의 Python으로 설치하고 실행했는지 |
| SQLAlchemy 관련 import 오류 | 고정한 `requirements.txt`와 실제 설치 버전이 같은지 |
| 기록이 다른 DB에 나타남 | 현재 작업 폴더와 `MLFLOW_TRACKING_URI` |
| `--C 0` 실행이 중단됨 | 양수만 받도록 한 입력 검사이며 정상 동작 |
| UI 포트를 사용할 수 없음 | 이미 사용 중인 포트인지 확인하고 다른 로컬 포트를 선택 |

## 정리와 생각할 점

UI는 실행한 터미널에서 `Ctrl+C`로 종료한다. 다음 편에서 사용할 DB와 아티팩트는 남긴다.

- 학습 성공과 모델 기록 성공을 같은 것으로 보고 있지 않은가.
- DB 파일만 남기고 `mlruns`를 잃으면 어떤 기록을 다시 읽을 수 없는가.
- 자동 기록 외에 데이터와 평가 조건을 설명할 정보는 무엇인가.

## 참고 자료

- [실험과 실행 추적](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-cli-runs?view=azureml-api-2)
- [메트릭과 파일 기록](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-view-metrics?view=azureml-api-2)
- [MLflow 모델 로깅과 버전 조건](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-mlflow-models?view=azureml-api-2)

[시리즈 목차](../), [다음: 02. 실행 비교와 메트릭 및 아티팩트 조회](../02-query-and-compare/)
