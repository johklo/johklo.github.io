---
title: "Kubeflow Pipelines 기초: 컴포넌트, 아티팩트, 로컬 실행에서 클러스터 제출까지"
description: "KFP v2 SDK로 파이프라인을 구성하고 로컬 실행, 아티팩트 전달, 품질 게이트와 클러스터 제출을 익힌다."
date: 2026-10-25T19:30:00+09:00
weight: 30
tags: ["mlops", "kubeflow", "pipelines", "hands-on"]
---

**파이프라인은 작업 지시서**, Kubernetes는 컨테이너와 자원을 관리하는 주방이다. Kubeflow는 노트북, 학습, 파이프라인을 묶은 ML 플랫폼이고, Argo Workflows는 별도 Kubernetes 워크플로 엔진이다. KFP는 ML 컴포넌트, 아티팩트, 실행 메타데이터를 정의한다.

KFP v2 Python SDK 기준이다. 로컬 실행은 Windows 네이티브를 지원하지 않으므로 Windows에서는 WSL2 Ubuntu를 사용한다. Bash 명령은 Linux, macOS, WSL2에서 실행한다.

## 1단계. 핵심 용어 익히기

| 용어 | 뜻 | 비유 |
| --- | --- | --- |
| Component | 입출력을 정의한 재사용 작업. Python 함수나 컨테이너 명령으로 작성한다. | 조리법 |
| Pipeline | 컴포넌트의 순서와 조건을 정의한다. | 작업 지시서 |
| Task | 특정 입력으로 컴포넌트를 호출한 실행이다. | 한 번의 조리 작업 |
| Parameter | 임계값, 날짜 등 컴포넌트 사이에 전달하는 작은 값과 문자열이다. | 주문서의 숫자, 메모 |
| Artifact | 파일과 메타데이터를 담는다. 대표 타입은 `Dataset`, `Model`, `Metrics`다. | 재료 상자, 완성 요리, 검사표 |
| Pipeline root | 아티팩트와 작업 출력의 저장 위치다. 로컬 디렉터리 또는 클러스터 객체 저장소 URI다. | 주방의 공용 보관소 |
| Run | 한 번의 실행 기록으로 입력, 상태, 결과를 담는다. | 주문 한 건 |
| Experiment | 관련 Run을 묶는 논리 그룹이다. | 메뉴 개발 프로젝트 |
| Compile, IR YAML | DSL 파이프라인을 실행 가능한 YAML로 변환한 과정과 결과다. | 실행 전 작업표 |
| Caching | 같은 컴포넌트와 입력의 결과를 재사용한다. | 준비된 재료 재사용 |
| Executor, driver | Executor는 사용자 코드, Driver는 입력 준비와 결과 기록을 맡는다. | 조리와 주문 기록 |

Parameter는 작은 값, Artifact는 데이터와 모델 파일에 맡긴다. 파이프라인은 작업 관계를 정의하지만 컨테이너끼리 Python 메모리를 공유하지 않으므로 파일은 아티팩트로 전달한다.

## 2단계. SDK 설치와 첫 컴포넌트

PyPI에서 확인한 KFP SDK 최신 2.x 버전은 `2.17.3`이다. 예제는 재현성을 위해 이 버전과 scikit-learn을 고정한다. 빈 작업 폴더에 가상환경을 만든다.

```bash
"$HOME/.local/bin/uv" venv --python 3.11 .venv
"$HOME/.local/bin/uv" pip install --python .venv/bin/python "kfp==2.17.3" "scikit-learn==1.7.2"
```

예제 파일 하나에 컴포넌트, 파이프라인, 아티팩트, 제어 흐름, 설정, 학습을 모았다. `@dsl.component`가 작업을, `@dsl.pipeline`이 의존성을 정의한다. 컴포넌트는 별도 실행되므로 필요한 모듈을 함수 안에서 import한다.

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

`compiler.Compiler().compile`은 파이프라인을 IR YAML로 저장한다. 다음 명령은 여섯 파일을 생성한다.

```bash
.venv/bin/python kfp_primer.py compile
```

관찰한 출력은 다음과 같다.

```text
compiled: intro-add.yaml
compiled: artifact-demo.yaml
compiled: control-demo.yaml
compiled: iris-training.yaml
compiled: task-config-demo.yaml
compiled: container-component-demo.yaml
```

`intro-add.yaml`에서 실제 생성된 IR의 일부이다. 컴포넌트 입력 형식과 파이프라인 이름이 선언되어 있다.

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

`kfp.local.init`은 로컬 실행을 설정한다. `SubprocessRunner(use_venv=False)`는 작업별 프로세스를 쓰되 현재 WSL 가상환경을 재사용하며, `add`는 정수 두 개를 더한다.

```bash
.venv/bin/python kfp_primer.py intro
```

실행 로그에서 `add` 작업의 출력과 파이프라인 성공 상태를 확인했다.

```text
Output: 5
Pipeline 'intro-add' finished with status SUCCESS
```

로컬 실행은 DSL과 컴포넌트 로직을 검증할 뿐 KFP UI, Kubernetes 스케줄링, 서버 인증, 객체 저장소를 검증하지 않는다.

## 4단계. Parameter와 Artifact 전달하기

작은 숫자와 문자열은 함수 인자로 전달하는 Parameter이다. 파일 데이터에는 `Output[Dataset]`과 `Input[Dataset]`을 사용한다. 출력 컴포넌트는 `data.path`에 파일을 쓰고, 다음 컴포넌트는 전달받은 아티팩트의 `data.path`를 읽는다. 작업들은 같은 Python 메모리를 공유하지 않는다. 앞 작업의 함수 변수 대신 KFP가 추적하는 출력 계약으로 연결한다.

`artifact_pipeline`은 세 값을 파일로 전달해 합계를 계산하고 개수와 합계를 `Metrics`에 기록한다.

```bash
.venv/bin/python kfp_primer.py artifacts
```

출력에서 합계와 Metrics 메타데이터를 확인한다.

```text
count=3, sum=6
Output: 6
metadata={'count': 3.0, 'sum': 6.0}
Pipeline 'artifact-demo' finished with status SUCCESS
```

KFP가 출력 아티팩트를 놓은 실제 경로는 다음 구조였다. 시각이 포함된 Run 디렉터리는 읽기 쉽도록 줄였다.

```text
local_outputs/artifact-demo-<실행 시각>/write-sample/data
local_outputs/artifact-demo-<실행 시각>/summarize/metrics
```

클러스터에서 `.path`는 컨테이너 경로이고 백엔드는 artifact URI에 저장한다. 큰 데이터와 모델은 `Dataset`, `Model`, `Metrics`로 전달한다.

## 5단계. 조건과 반복 흐름

`control_pipeline`은 조건 분기로 작업을 고르고 `dsl.ParallelFor`로 세 입력을 처리한 뒤 `dsl.Collected`로 결과를 전달한다.

```bash
.venv/bin/python kfp_primer.py control
```

KFP `2.17.3`의 현재 로컬 실행에서 이 예제는 실행되었다. 선택된 분기와 반복 출력의 일부이다.

```text
selected: medium
Output: 2
Output: 3
Output: 4
Output: 9.0
Pipeline 'control-demo' finished with status SUCCESS
```

공식 가이드는 일부 제어 흐름을 제한한다. 여기서는 KFP `2.17.3`의 단순 조건, 반복, 수집만 확인했으며 복잡한 중첩과 클러스터 동작은 백엔드에서 검증해야 한다.

## 6단계. 작업 환경과 리소스 설정

`task_config_pipeline`에는 다음 SDK 설정이 들어 있다.

- `set_caching_options(enable_caching=False)`는 캐시 사용을 끈다. 데이터 소스나 외부 상태가 입력값에 나타나지 않는 작업은 캐시가 오래된 결과를 재사용할 수 있다.
- `set_retry(num_retries=1)`은 실패 작업의 재시도 정책을 설정한다.
- `set_cpu_limit("1")`, `set_memory_limit("512Mi")`는 클러스터 컨테이너의 리소스 제한을 설정한다.
- `set_env_variable("PRIMER_MODE", "local")`은 컨테이너 환경변수를 설정한다.

이 설정 파이프라인은 IR YAML로 컴파일했다. 로컬 실행은 캐싱, 재시도, CPU와 메모리 제한을 적용하지 않는다. 따라서 이 설정을 실제로 검증하려면 클러스터 실행이 필요하다.

`packages_to_install`은 컨테이너 시작 시 설치할 Python 패키지를 지정한다. OS 라이브러리와 인증서, 사전 빌드 코드는 사용자 `base_image`에 넣는다. Iris는 원격 패키지를 선언하고 로컬에서는 가상환경의 scikit-learn을 쓴다.

`@dsl.container_component`는 이미지, 명령, 인자를 컨테이너 사양으로 작성한다. `container_hello`는 컴파일만 확인했으며, SubprocessRunner는 컨테이너 이미지를 실행하지 않는다. DockerRunner와 Kubernetes 클러스터는 검증하지 않았다.

## 7단계. Iris 학습, 평가, 품질 게이트

작은 ML 파이프라인은 데이터를 준비하고, 학습하고, 평가한 뒤, 기준보다 낮은 정확도면 실패해야 한다. 예제는 scikit-learn에 포함된 Iris 데이터를 사용해 네 단계로 실행한다.

1. `create_iris_data`는 학습 112행과 테스트 38행을 `Dataset` 파일로 쓴다.
2. `train_iris`는 학습 행으로 Logistic Regression 모델을 학습하고 `Model` 아티팩트 경로에 저장한다.
3. `evaluate_iris`는 테스트 행의 정확도를 계산하고 `Metrics`에 기록한다.
4. `quality_gate`는 정확도가 기본 기준 `0.9`보다 낮으면 예외를 내 Run을 실패시킨다.

다음 명령은 기본 기준으로 전체 파이프라인을 로컬 실행한다.

```bash
.venv/bin/python kfp_primer.py iris
```

이번 실행의 출력은 아래와 같았다. 정확도는 테스트 분할 기준 `0.947`이며, 기본 기준을 통과했다.

```text
Iris rows: 112 train, 38 test
trained rows: 112
accuracy: 0.947
quality gate passed: accuracy=0.947, baseline=0.900
Pipeline 'iris-training' finished with status SUCCESS
```

학습 결과 파일과 평가 지표는 각 작업의 아티팩트 경로에 따로 기록되었다. 운영 기준이나 배포 정책도 품질 게이트의 실패 조건으로 둔다.

## 8단계. 클러스터에 제출하기

클러스터 제출은 설명만 다룬다. 서버나 kind를 만들지 않았고 `Client` 요청도 보내지 않았다. KFP 설치에는 Kubernetes, 저장소, 인증 구성이 필요하다.

`kfp.Client(host=...)`로 연결하고 `create_experiment(name=...)`로 실험을 만든다. Python 함수는 `create_run_from_pipeline_func(...)`, IR 파일은 `create_run_from_pipeline_package(...)`로 제출한다. UI에서 Run과 로그를 확인하고 `ml-pipeline-ui`를 포트 포워딩해 접속한다.

Python SDK 버전과 KFP 서버 버전은 별도이다. 이 안내에서 확인한 PyPI SDK는 `2.17.3`이고, 공식 standalone 설치 예시의 서버 버전은 `2.17.2`다. 설치 태그에 SDK 버전을 그대로 넣지 말고, 서버 설치 문서가 지정한 서버 버전과 기능 호환성을 확인한다.

로컬 kind 기반 standalone KFP, 아티팩트 저장소, 실행 패치 구성은 [Kubernetes에서 네 작업 실행하기](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/)의 실습 기록을 참고한다. 그 글은 kind `0.27.0`, KFP standalone `2.4.1`, SeaweedFS 아티팩트 저장소 구성이다. 이 가이드의 예제는 클러스터 없이 로컬에서 실행했다. 설치 절차는 [공식 standalone 설치 문서](https://www.kubeflow.org/docs/components/pipelines/operator-guides/installation/)를 기준으로 삼고, 인증과 보안 설정을 운영 배포 수준으로 점검해야 한다.

## 9단계. Feast와 MLflow 연결

KFP는 실행을 조정하고 Feast는 피처, MLflow는 실험을 관리한다. 컴포넌트가 `get_historical_features` 결과를 Dataset으로 넘기고, 학습 작업은 MLflow에 파라미터, 지표, 모델을 기록하거나 등록한다.

큰 데이터와 모델은 artifact `.path`의 파일로 전달하며 클러스터에서는 MinIO나 S3 호환 저장소에 둔다. KFP는 학습의 데이터 조회, 학습, 평가, 등록이나 배치 추론의 입력, 예측, 결과 저장을 오케스트레이션한다.

## 10단계. 자주 만나는 함정

| 함정 | 이유와 대응 |
| --- | --- |
| 노트북이나 PC 경로를 Pod 경로로 전달 | 클러스터 Pod는 개발 PC의 파일을 볼 수 없다. 이미지나 공유 객체 저장소에 입력을 준비하고, artifact URI와 `.path`를 사용한다. |
| `localhost`를 개발 PC로 생각 | Pod 안의 `localhost`는 해당 Pod 자신이다. 외부 서비스를 호출할 때는 클러스터 DNS 이름, 서비스 주소, 인증 설정을 사용한다. |
| 컨테이너 이미지에 패키지가 없음 | 로컬 venv에 설치된 패키지는 클러스터 Pod에 자동 전달되지 않는다. `packages_to_install` 또는 고정된 사용자 이미지를 준비한다. |
| 캐시가 이전 결과를 반환 | 외부 데이터 버전이 task 입력에 포함되지 않으면 같은 입력으로 판단될 수 있다. 데이터 버전을 입력으로 명시하거나 캐시를 끈다. |
| 비밀값을 pipeline parameter로 전달 | 파라미터와 실행 기록, UI에 값이 노출될 수 있다. Secret, 워크로드 아이덴티티, 백엔드의 인증 수단을 사용한다. |
| SDK와 서버 버전 불일치 | SDK가 지원하는 IR이나 API를 서버가 지원하지 않을 수 있다. SDK와 서버 버전을 별도로 확인한다. |
| Windows 네이티브에서 local runner 실행 | SDK 로컬 실행의 프로세스, 경로 동작이 Windows 네이티브와 맞지 않을 수 있다. 이 글처럼 WSL2 Linux 환경에서 실행한다. |

## 11단계. 참고 링크

아래 공식 페이지는 HTTP 요청으로 상태 코드 `200`을 확인했다. KFP 사이트의 문서 구조는 바뀔 수 있으므로 링크가 이동하면 현행 공식 문서의 canonical 주소를 따른다.

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