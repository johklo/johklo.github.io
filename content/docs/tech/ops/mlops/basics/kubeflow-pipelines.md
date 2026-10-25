---
title: "Kubeflow Pipelines 기초: 컴포넌트, 아티팩트, 로컬 실행에서 클러스터 제출까지"
description: "KFP v2 SDK의 파이프라인 구성부터 로컬 실행, 아티팩트 전달, 품질 게이트와 클러스터 제출 준비까지 단계별로 익힙니다."
date: 2026-10-25T19:30:00+09:00
weight: 30
tags: ["mlops", "kubeflow", "pipelines", "hands-on"]
---

식당에 비유하면, **파이프라인은 작업 지시서와 주방 배정**입니다. 지시서에 준비, 조리, 품질 검사의 순서를 적으면 KFP가 작업을 나누어 실행하고 상태를 기록합니다. Kubernetes는 컨테이너와 자원을 관리하는 주방이고, Kubeflow는 노트북, 학습, 파이프라인을 묶은 ML 플랫폼입니다. Argo Workflows는 Kubernetes의 일반 워크플로 엔진으로 KFP와 별도 제품입니다. KFP는 ML 컴포넌트, 아티팩트, 실행 메타데이터를 정의합니다.

이 글은 KFP v2 Python SDK를 기준으로 합니다. KFP 로컬 실행은 Windows 네이티브 Python 환경을 지원하지 않으므로 Windows 사용자는 WSL2의 Ubuntu에서 진행합니다. Bash 명령은 Linux, macOS, WSL2에서 사용할 수 있습니다.

## 1단계. 핵심 용어 익히기

| 용어 | 뜻 | 비유 |
| --- | --- | --- |
| Component | 입력과 출력을 정한 재사용 가능한 작업 정의입니다. Python 함수 또는 컨테이너 명령으로 작성합니다. | 조리법 |
| Pipeline | 컴포넌트 간 선후 관계와 조건을 정의한 전체 흐름입니다. | 작업 지시서 |
| Task | 파이프라인 안에서 특정 입력으로 컴포넌트를 호출한 실행 단위입니다. | 한 번 배정된 조리 작업 |
| Parameter | 작은 값이나 문자열을 컴포넌트 사이에 전달합니다. 예를 들어 임계값이나 날짜입니다. | 주문서의 숫자, 메모 |
| Artifact | 파일처럼 큰 결과와 관련 메타데이터를 담는 객체입니다. `Dataset`, `Model`, `Metrics`가 대표 타입입니다. | 재료 상자, 완성 요리, 검사표 |
| Pipeline root | 실행 중 만들어진 아티팩트와 작업 출력을 저장하는 기준 위치입니다. 로컬에서는 디렉터리, 클러스터에서는 객체 저장소 URI가 될 수 있습니다. | 주방의 공용 보관소 |
| Run | 파이프라인을 한 번 실행한 기록입니다. 입력값, 상태, 작업 결과를 구분합니다. | 주문 한 건 |
| Experiment | 관련된 Run을 묶어 비교하는 논리적 그룹입니다. | 같은 메뉴 개발 프로젝트 |
| Compile, IR YAML | DSL로 작성한 파이프라인을 실행 가능한 YAML 중간 표현으로 변환하는 과정과 결과입니다. | 실행 전 작업표로 변환 |
| Caching | 같은 컴포넌트와 입력의 결과를 재사용해 반복 계산을 줄입니다. | 같은 주문의 준비된 재료 재사용 |
| Executor, driver | Executor는 컴포넌트 사용자 코드를 실행합니다. Driver는 KFP 런타임에서 입력 아티팩트 준비와 실행 결과 기록을 연결합니다. | 조리대와 배식, 주문 기록 담당 |

Parameter에는 작은 값, Artifact에는 데이터 파일과 모델 파일을 맡깁니다. 파이프라인 코드는 작업 간 관계를 표현하지만, 각 컨테이너의 Python 메모리를 공유하지는 않습니다. 파일을 넘길 때는 아티팩트 연결을 사용합니다.

## 2단계. SDK 설치와 첫 컴포넌트

PyPI에서 확인한 KFP SDK 최신 2.x 버전은 `2.17.3`입니다. 아래 예제는 재현성을 위해 이 버전과 scikit-learn을 고정합니다. 빈 작업 폴더를 만들고 그 안에서 가상환경을 만듭니다.

```bash
"$HOME/.local/bin/uv" venv --python 3.11 .venv
"$HOME/.local/bin/uv" pip install --python .venv/bin/python "kfp==2.17.3" "scikit-learn==1.7.2"
```

아래 파일은 이 안내의 컴포넌트, 파이프라인, 아티팩트, 제어 흐름, 설정, 학습 예제를 한 곳에 모은 완전한 실행 파일입니다. `@dsl.component`는 Python 함수에서 컴포넌트를 만들고, `@dsl.pipeline`은 작업 간 의존성을 정의합니다. 컴포넌트 본문은 별도 실행 단위로 직렬화되므로, 사용하는 모듈은 함수 안에서 import하도록 작성했습니다.

`kfp_primer.py`:

```python
import argparse
import csv
import os

from kfp import compiler, dsl, local
from kfp.dsl import Dataset, Input, Metrics, Model, Output


@dsl.component(base_image="python:3.11")
def add(a: int, b: int) -> int:
    return a + b


@dsl.pipeline(name="intro-add")
def add_pipeline(a: int = 2, b: int = 3):
    add(a=a, b=b)


@dsl.component(base_image="python:3.11")
def write_sample(data: Output[Dataset]):
    with open(data.path, "w", encoding="utf-8") as stream:
        stream.write("value\n1\n2\n3\n")


@dsl.component(base_image="python:3.11")
def summarize(data: Input[Dataset], metrics: Output[Metrics]) -> int:
    with open(data.path, encoding="utf-8") as stream:
        values = [int(line) for line in stream.read().splitlines()[1:]]
    total = sum(values)
    metrics.log_metric("count", len(values))
    metrics.log_metric("sum", total)
    print(f"count={len(values)}, sum={total}")
    return total


@dsl.pipeline(name="artifact-demo")
def artifact_pipeline():
    source = write_sample()
    summarize(data=source.outputs["data"])


@dsl.component(base_image="python:3.11")
def label(text: str) -> str:
    print(f"selected: {text}")
    return text


@dsl.component(base_image="python:3.11")
def plus_one(value: int) -> int:
    return value + 1


@dsl.component(base_image="python:3.11")
def sum_values(values: list) -> float:
    return float(sum(values))


@dsl.pipeline(name="control-demo")
def control_pipeline(score: float = 0.8):
    with dsl.If(score >= 0.9):
        label(text="high")
    with dsl.Elif(score >= 0.7):
        label(text="medium")
    with dsl.Else():
        label(text="low")
    with dsl.ParallelFor(items=[1, 2, 3]) as item:
        task = plus_one(value=item)
    sum_values(values=dsl.Collected(task.output))


@dsl.component(base_image="python:3.11", packages_to_install=["scikit-learn==1.7.2"])
def create_iris_data(data: Output[Dataset]):
    import csv
    import numpy as np
    from sklearn.datasets import load_iris
    from sklearn.model_selection import train_test_split

    features, labels = load_iris(return_X_y=True)
    train_x, test_x, train_y, test_y = train_test_split(
        features, labels, test_size=0.25, random_state=42, stratify=labels
    )
    with open(data.path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["split", "f0", "f1", "f2", "f3", "target"])
        for split, rows, targets in (
            ("train", train_x, train_y),
            ("test", test_x, test_y),
        ):
            for row, target in zip(rows, targets):
                writer.writerow([split, *np.asarray(row).tolist(), int(target)])
    print("Iris rows: 112 train, 38 test")


@dsl.component(base_image="python:3.11", packages_to_install=["scikit-learn==1.7.2"])
def train_iris(data: Input[Dataset], model: Output[Model]):
    import csv
    import joblib
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    rows = []
    with open(data.path, newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["split"] == "train":
                rows.append(row)
    features = np.asarray([[float(row[f"f{i}"]) for i in range(4)] for row in rows])
    labels = np.asarray([int(row["target"]) for row in rows])
    estimator = LogisticRegression(max_iter=300).fit(features, labels)
    joblib.dump(estimator, model.path)
    print(f"trained rows: {len(rows)}")


@dsl.component(base_image="python:3.11", packages_to_install=["scikit-learn==1.7.2"])
def evaluate_iris(
    data: Input[Dataset], model: Input[Model], metrics: Output[Metrics]
) -> float:
    import csv
    import joblib
    import numpy as np
    from sklearn.metrics import accuracy_score

    rows = []
    with open(data.path, newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["split"] == "test":
                rows.append(row)
    features = np.asarray([[float(row[f"f{i}"]) for i in range(4)] for row in rows])
    labels = np.asarray([int(row["target"]) for row in rows])
    accuracy = float(accuracy_score(labels, joblib.load(model.path).predict(features)))
    metrics.log_metric("accuracy", accuracy)
    print(f"accuracy: {accuracy:.3f}")
    return accuracy


@dsl.component(base_image="python:3.11")
def quality_gate(accuracy: float, baseline: float = 0.9):
    if accuracy < baseline:
        raise RuntimeError(f"accuracy {accuracy:.3f} is below baseline {baseline:.3f}")
    print(f"quality gate passed: accuracy={accuracy:.3f}, baseline={baseline:.3f}")


@dsl.pipeline(name="iris-training")
def iris_pipeline(baseline: float = 0.9):
    data = create_iris_data()
    model = train_iris(data=data.outputs["data"])
    evaluation = evaluate_iris(data=data.outputs["data"], model=model.outputs["model"])
    quality_gate(accuracy=evaluation.outputs["Output"], baseline=baseline)


@dsl.component(base_image="python:3.11", packages_to_install=["pyyaml==6.0.3"])
def report_mode() -> str:
    import os
    mode = os.environ.get("PRIMER_MODE", "not-set")
    print(f"PRIMER_MODE={mode}")
    return mode


@dsl.pipeline(name="task-config-demo")
def task_config_pipeline():
    task = report_mode()
    task.set_caching_options(enable_caching=False)
    task.set_retry(num_retries=1)
    task.set_cpu_limit("1")
    task.set_memory_limit("512Mi")
    task.set_env_variable("PRIMER_MODE", "local")


@dsl.container_component
def container_hello():
    return dsl.ContainerSpec(
        image="python:3.11-slim",
        command=["python", "-c"],
        args=["print('container component')"],
    )


@dsl.pipeline(name="container-component-demo")
def container_pipeline():
    container_hello()


def compile_pipelines():
    targets = (
        (add_pipeline, "intro-add.yaml"),
        (artifact_pipeline, "artifact-demo.yaml"),
        (control_pipeline, "control-demo.yaml"),
        (iris_pipeline, "iris-training.yaml"),
        (task_config_pipeline, "task-config-demo.yaml"),
        (container_pipeline, "container-component-demo.yaml"),
    )
    for pipeline, filename in targets:
        compiler.Compiler().compile(pipeline, package_path=filename)
        print(f"compiled: {filename}")


def run_local(pipeline):
    local.init(
        runner=local.SubprocessRunner(use_venv=False),
        pipeline_root="./local_outputs",
    )
    pipeline()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("compile", "intro", "artifacts", "control", "iris", "config"),
    )
    parser.add_argument("--score", type=float, default=0.8)
    parser.add_argument("--baseline", type=float, default=0.9)
    args = parser.parse_args()
    if args.action == "compile":
        compile_pipelines()
    elif args.action == "intro":
        run_local(add_pipeline)
    elif args.action == "artifacts":
        run_local(artifact_pipeline)
    elif args.action == "control":
        local.init(
            runner=local.SubprocessRunner(use_venv=False),
            pipeline_root="./local_outputs",
        )
        control_pipeline(score=args.score)
    elif args.action == "iris":
        local.init(
            runner=local.SubprocessRunner(use_venv=False),
            pipeline_root="./local_outputs",
        )
        iris_pipeline(baseline=args.baseline)
    else:
        run_local(task_config_pipeline)


if __name__ == "__main__":
    main()
```

`compiler.Compiler().compile`은 파이프라인을 IR YAML로 저장합니다. 파일은 `intro-add.yaml`처럼 선택한 이름으로 생성됩니다. 다음 명령은 여섯 개의 파이프라인을 컴파일합니다.

```bash
.venv/bin/python kfp_primer.py compile
```

관찰한 출력은 다음과 같습니다.

```text
compiled: intro-add.yaml
compiled: artifact-demo.yaml
compiled: control-demo.yaml
compiled: iris-training.yaml
compiled: task-config-demo.yaml
compiled: container-component-demo.yaml
```

`intro-add.yaml`에서 실제 생성된 IR의 일부입니다. 컴포넌트 입력 형식과 파이프라인 이름이 선언되어 있습니다.

```yaml
# PIPELINE DEFINITION
# Name: intro-add
# Inputs:
#    a: int [Default: 2.0]
#    b: int [Default: 3.0]
components:
  comp-add:
    executorLabel: exec-add
    inputDefinitions:
      parameters:
        a:
          parameterType: NUMBER_INTEGER
        b:
          parameterType: NUMBER_INTEGER
```

## 3단계. SubprocessRunner로 로컬 실행

`kfp.local.init`은 로컬 실행 설정을 초기화합니다. `SubprocessRunner(use_venv=False)`는 각 작업 코드를 별도 프로세스로 실행하되, 별도 작업 가상환경을 만들지 않고 현재 WSL 가상환경을 사용합니다. 이 예제의 `add` 컴포넌트는 정수 두 개를 더합니다.

```bash
.venv/bin/python kfp_primer.py intro
```

실행 로그에서 `add` 작업의 출력과 파이프라인 성공 상태를 확인했습니다.

```text
Output: 5
Pipeline 'intro-add' finished with status SUCCESS
```

로컬 실행은 DSL과 컴포넌트 로직을 검증할 뿐 KFP UI, Kubernetes 스케줄링, 서버 인증, 객체 저장소를 검증하지 않습니다.

## 4단계. Parameter와 Artifact 전달하기

작은 숫자와 문자열은 함수 인자로 전달하는 Parameter입니다. 파일 데이터에는 `Output[Dataset]`과 `Input[Dataset]`을 사용합니다. 출력 컴포넌트는 `data.path`에 파일을 쓰고, 다음 컴포넌트는 전달받은 아티팩트의 `data.path`를 읽습니다. 작업들은 같은 Python 메모리를 공유하지 않습니다. 앞 작업의 함수 변수 대신 KFP가 추적하는 출력 계약으로 연결합니다.

`artifact_pipeline`은 CSV형 텍스트를 작성하고, 다음 작업은 세 값을 읽어 합계를 계산합니다. `Metrics` 아티팩트에 개수와 합계도 기록합니다. 로컬 실행 명령은 다음과 같습니다.

```bash
.venv/bin/python kfp_primer.py artifacts
```

실제 출력에서 합계와 Metrics 메타데이터를 확인했습니다.

```text
count=3, sum=6
Output: 6
metadata={'count': 3.0, 'sum': 6.0}
Pipeline 'artifact-demo' finished with status SUCCESS
```

KFP가 출력 아티팩트를 놓은 실제 경로는 다음 구조였습니다. 시각이 포함된 Run 디렉터리는 읽기 쉽도록 줄였습니다.

```text
local_outputs/artifact-demo-<실행 시각>/write-sample/data
local_outputs/artifact-demo-<실행 시각>/summarize/metrics
```

클러스터에서 `.path`는 컨테이너 안 경로이며 백엔드는 artifact URI로 결과를 저장합니다. 큰 데이터와 모델은 Parameter가 아닌 `Dataset`, `Model`, `Metrics`로 전달합니다.

## 5단계. 조건과 반복 흐름

`control_pipeline`은 `dsl.If`, `dsl.Elif`, `dsl.Else`로 점수 구간에 따라 작업을 선택하고, `dsl.ParallelFor`로 세 입력에 작업을 반복합니다. 반복 결과는 `dsl.Collected`로 모아 다음 컴포넌트에 전달합니다.

```bash
.venv/bin/python kfp_primer.py control
```

KFP `2.17.3`의 현재 로컬 실행에서 이 예제는 실행되었습니다. 선택된 분기와 반복 출력의 일부입니다.

```text
selected: medium
Output: 2
Output: 3
Output: 4
Output: 9.0
Pipeline 'control-demo' finished with status SUCCESS
```

공식 로컬 실행 가이드는 제어 흐름 일부를 제한 사항으로 안내합니다. 여기서는 KFP `2.17.3`의 단순 조건, 반복, 수집만 통과했습니다. 복잡한 중첩과 클러스터 동작은 백엔드에서도 검증합니다.

## 6단계. 작업 환경과 리소스 설정

`task_config_pipeline`에는 다음 SDK 설정이 들어 있습니다.

- `set_caching_options(enable_caching=False)`는 캐시 사용을 끕니다. 데이터 소스나 외부 상태가 입력값에 나타나지 않는 작업은 캐시가 오래된 결과를 재사용할 수 있습니다.
- `set_retry(num_retries=1)`은 실패 작업의 재시도 정책을 설정합니다.
- `set_cpu_limit("1")`, `set_memory_limit("512Mi")`는 클러스터 컨테이너의 리소스 제한을 설정합니다.
- `set_env_variable("PRIMER_MODE", "local")`은 컨테이너 환경변수를 설정합니다.

이 설정 파이프라인은 IR YAML로 컴파일했습니다. 로컬 실행은 캐싱, 재시도, CPU와 메모리 제한을 적용하지 않습니다. 따라서 이 설정을 실제로 검증하려면 클러스터 실행이 필요합니다.

`@dsl.component(packages_to_install=[...])`는 컨테이너 시작 때 설치할 Python 패키지를 지정합니다. OS 라이브러리, 인증서, 사전 빌드 코드는 `base_image`에 사용자 이미지를 지정하는 방식이 적합합니다. Iris 컴포넌트는 원격용 패키지를 선언하고, 로컬에서는 가상환경에 설치한 scikit-learn을 사용합니다.

`@dsl.container_component`는 이미지, 명령, 인자를 컨테이너 사양으로 작성합니다. `container_hello`는 컴파일만 확인했으며, SubprocessRunner는 컨테이너 이미지를 실행하지 않습니다. DockerRunner와 Kubernetes 클러스터는 검증하지 않았습니다.

## 7단계. Iris 학습, 평가, 품질 게이트

작은 ML 파이프라인은 데이터를 준비하고, 학습하고, 평가한 뒤, 기준보다 낮은 정확도면 실패해야 합니다. 예제는 scikit-learn에 포함된 Iris 데이터를 사용해 네 단계로 실행합니다.

1. `create_iris_data`는 112개 학습 행과 38개 테스트 행을 `Dataset` 아티팩트 파일로 씁니다.
2. `train_iris`는 학습 행으로 Logistic Regression 모델을 학습하고 `Model` 아티팩트 경로에 저장합니다.
3. `evaluate_iris`는 테스트 행의 정확도를 계산하고 `Metrics`에 기록합니다.
4. `quality_gate`는 기본 기준인 `0.9`보다 낮으면 예외를 내 Run을 실패시킵니다.

다음 명령은 기본 기준으로 전체 파이프라인을 로컬 실행합니다.

```bash
.venv/bin/python kfp_primer.py iris
```

이번 실행의 출력은 아래와 같았습니다. 정확도는 테스트 분할 기준 `0.947`이며, 기본 기준을 통과했습니다.

```text
Iris rows: 112 train, 38 test
trained rows: 112
accuracy: 0.947
quality gate passed: accuracy=0.947, baseline=0.900
Pipeline 'iris-training' finished with status SUCCESS
```

학습 결과 파일과 평가 지표는 각 작업의 아티팩트 경로에 따로 기록되었습니다. 운영 기준을 높이거나 모델 배포 정책을 추가하려면 품질 게이트를 그 정책의 명시적인 실패 지점으로 둡니다.

## 8단계. 클러스터에 제출하기

클러스터 제출은 설명만 다룹니다. 서버나 kind를 만들지 않았고 `Client` 요청도 보내지 않았습니다. KFP 설치에는 Kubernetes, 저장소, 인증 구성이 필요합니다.

`kfp.Client(host=...)`로 연결하고 `create_experiment(name=...)`로 Run을 묶을 실험을 만듭니다. Python 함수는 `create_run_from_pipeline_func(iris_pipeline, arguments={...}, experiment_name=...)`, IR 파일은 `create_run_from_pipeline_package("iris-training.yaml", arguments={...}, experiment_name=...)`로 제출합니다. Run 상태와 로그는 UI에서 확인하며, `ml-pipeline-ui`로 포트 포워딩해 브라우저에서 접속합니다.

Python SDK 버전과 KFP 서버 버전은 별도입니다. 이 안내에서 확인한 PyPI SDK는 `2.17.3`이고, 공식 standalone 설치 문서의 KFP 배포 예시는 서버 릴리스 버전 `2.17.2`를 가리킵니다. 설치 태그에 SDK 버전을 그대로 넣지 말고, 서버 설치 문서가 지정한 서버 버전과 기능 호환성을 확인합니다.

로컬 kind 기반 standalone KFP, 아티팩트 저장소, 실행 패치 구성은 [Kubernetes에서 네 작업 실행하기](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/)의 실습 기록을 참고합니다. 그 글은 kind `0.27.0`, KFP standalone `2.4.1`, SeaweedFS 아티팩트 저장소 구성을 다룹니다. 이 가이드의 예제는 클러스터 없이 로컬에서 실행했습니다. 설치 절차는 [공식 standalone 설치 문서](https://www.kubeflow.org/docs/components/pipelines/operator-guides/installation/)를 기준으로 삼고, 인증과 보안 설정을 운영 배포 수준으로 점검해야 합니다.

## 9단계. Feast와 MLflow 연결

KFP가 실행을 조정하고 Feast와 MLflow가 피처, 실험 추적을 담당합니다. 컴포넌트가 Feast `get_historical_features`로 학습 피처를 조회해 Dataset으로 넘기고, 학습 작업이 MLflow에 파라미터, 지표, 모델을 기록하거나 등록할 수 있습니다.

큰 데이터와 모델은 artifact `.path`의 파일로 전달하며 클러스터에서는 MinIO나 S3 호환 저장소에 둡니다. KFP는 학습의 데이터 조회, 학습, 평가, 등록이나 배치 추론의 입력, 예측, 결과 저장을 오케스트레이션합니다.

## 10단계. 자주 만나는 함정

| 함정 | 이유와 대응 |
| --- | --- |
| 노트북이나 PC 경로를 Pod 경로로 전달 | 클러스터 Pod는 개발 PC의 파일을 볼 수 없습니다. 이미지나 공유 객체 저장소에 입력을 준비하고, artifact URI와 `.path`를 사용합니다. |
| `localhost`를 개발 PC로 생각 | Pod 안의 `localhost`는 해당 Pod 자신입니다. 외부 서비스를 호출할 때는 클러스터 DNS 이름, 서비스 주소, 인증 설정을 사용합니다. |
| 컨테이너 이미지에 패키지가 없음 | 로컬 venv에 설치된 패키지는 클러스터 Pod에 자동 전달되지 않습니다. `packages_to_install` 또는 고정된 사용자 이미지를 준비합니다. |
| 캐시가 이전 결과를 반환 | 외부 데이터 버전이 task 입력에 포함되지 않으면 같은 입력으로 판단될 수 있습니다. 데이터 버전을 입력으로 명시하거나 캐시를 끕니다. |
| 비밀값을 pipeline parameter로 전달 | 파라미터와 실행 기록, UI에 값이 노출될 수 있습니다. Secret, 워크로드 아이덴티티, 백엔드의 인증 수단을 사용합니다. |
| SDK와 서버 버전 불일치 | SDK가 지원하는 IR이나 API를 서버가 지원하지 않을 수 있습니다. SDK와 서버 버전을 별도로 확인합니다. |
| Windows 네이티브에서 local runner 실행 | SDK 로컬 실행의 프로세스, 경로 동작이 Windows 네이티브와 맞지 않을 수 있습니다. 이 글처럼 WSL2 Linux 환경에서 실행합니다. |

## 11단계. 참고 링크

아래 공식 페이지는 HTTP 요청으로 상태 코드 `200`을 확인했습니다. KFP 사이트의 문서 구조는 바뀔 수 있으므로 링크가 이동하면 현행 공식 문서의 canonical 주소를 따릅니다.

- [Kubeflow Pipelines 개요](https://www.kubeflow.org/docs/components/pipelines/overview/)
- [Standalone 설치 안내](https://www.kubeflow.org/docs/components/pipelines/operator-guides/installation/)
- [컴포넌트 만들기](https://www.kubeflow.org/docs/components/pipelines/user-guides/components/)
- [첫 파이프라인 시작하기](https://www.kubeflow.org/docs/components/pipelines/getting-started/)
- [파이프라인 실행 안내](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/run-a-pipeline/)
- [데이터 처리 안내](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/)
- [Artifact 전달 및 추적](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/artifacts/)
- [로컬 실행 안내](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/execute-kfp-pipelines-locally/)
- [제어 흐름](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/control-flow/)
- [컴파일과 IR YAML](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/compile-a-pipeline/), [IR YAML 개념](https://www.kubeflow.org/docs/components/pipelines/concepts/ir-yaml/)
- [KFP Client SDK API](https://kubeflow-pipelines.readthedocs.io/en/stable/source/client.html), [SDK 전체 참조](https://www.kubeflow.org/docs/components/pipelines/reference/sdk/)

## 관련 글

- [Kubeflow 운영 설계 가이드](/docs/tech/ops/mlops/kubeflow/)
- [ML 플랫폼 파이프라인 실습](/docs/tech/ops/mlops/labs/ml-platform-labs-04-pipelines/)
- [실험, 피처, 파이프라인 4, 5장, 클러스터 실행](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/)
- [MLflow 기초](/docs/tech/ops/mlops/basics/mlflow/)
- [Feast 기초](/docs/tech/ops/mlops/basics/feast/)
- [BentoML 기초](/docs/tech/ops/mlops/basics/bentoml/)