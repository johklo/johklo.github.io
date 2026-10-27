---
title: "04. AML 연결과 원격 학습 Job"
description: "로컬 코드를 AML에 연결해 기록하고 같은 학습을 원격 command Job으로 실행한다."
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 40
tags: ["mlflow", "mlops", "azure-machine-learning"]
aliases:
  - "/docs/tech/mlflow-azure-machine-learning/04-azureml-tracking-and-jobs/"
---

AML 전환을 기록 대상 변경과 실행 위치 변경으로 나눈다. 먼저 로컬 학습 결과를 AML에 기록하고, 이어 같은 코드를 원격 Job으로 제출한다.

## 준비 조건

01~03편의 실습 폴더, `train.py`, `compare.py`, `inspect_run.py`를 유지한다. AML workspace에 접근할 계정과 네트워크가 필요하다. 원격 Job에는 CPU compute cluster도 필요하다. 이 편은 실행 결과를 기록하고 선택하는 단계이며 모델 등록은 [05편](/docs/tech/ops/mlops/labs/05-model-registration/)에서 진행한다.

## 로컬 학습의 기록 위치를 AML로 변경

AML workspace가 필요하다. 없으면 [초기 리소스 만들기](https://learn.microsoft.com/en-us/azure/machine-learning/quickstart-create-resources?view=azureml-api-2)를 참고한다. 생성과 사용에는 연결 스토리지 비용도 든다.

### 인증과 권한

AML 연결에 필요한 플러그인은 원격 기록 단계에서 설치한다.

`requirements-azure.txt`:

```text
-r requirements.txt
azureml-mlflow==1.62.0.post6
```

로컬에서는 Azure CLI 사용자로 인증하며 workspace 실험과 Job 권한이 필요하다. 05편 등록에는 모델 생성, 갱신 권한도 필요하다. `AzureML Data Scientist`는 학습 권한의 한 예이며 실제 역할은 조직 정책에 맞춘다.

[Workspace 권한 문서](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-assign-roles?view=azureml-api-2#mlflow-operations)에서 실험, Job, 모델 조회, 생성, 갱신 권한을 구분한다. 기록 권한만으로 등록할 수 없고, `AzureML Data Scientist`에는 compute 생성, 삭제가 포함되지 않는다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements-azure.txt
.\.venv\Scripts\python.exe -m pip check

az login
az extension add --name ml --upgrade

$subscription = "<subscription-id>"
$resourceGroup = "<resource-group>"
$workspace = "<workspace-name>"
az account set --subscription $subscription
```

CLI 로그인은 대화형 학습용이다. 무인 CI에서는 별도 인증, 권한을 설계하고 비밀 정보를 코드나 Job YAML에 넣지 않는다.

### Tracking URI 조회

```powershell
$trackingUri = az ml workspace show --name $workspace --resource-group $resourceGroup --subscription $subscription --query mlflow_tracking_uri --output tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($trackingUri)) {
    throw "Could not read the workspace tracking URI"
}

$env:MLFLOW_TRACKING_URI = $trackingUri.Trim()
$env:MLFLOW_REGISTRY_URI = $env:MLFLOW_TRACKING_URI
$env:MLFLOW_EXPERIMENT_NAME = "mlflow-wine-study"
```

CLI가 반환한 Tracking URI를 그대로 사용하고 리전 이름으로 조립하지 않는다. Private Link workspace는 네트워크 경로와 DNS도 확인한다.

URI 설정만으로 인증, 통신이 검증되지는 않는다. experiment 조회나 run 시작으로 연결을 확인한다.

[연결 설정 문서](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-configure-tracking?view=azureml-api-2)는 Azure CLI, 환경 자격 증명, 관리 ID 등 실행 환경별 인증을 안내한다. 이 실습은 CLI를 쓰며 URI에 비밀이나 토큰을 붙이지 않는다.

### 같은 코드로 재실행

```powershell
foreach ($c in @("0.01", "0.1", "1.0")) {
    .\.venv\Scripts\python.exe .\src\train.py --C $c
    if ($LASTEXITCODE -ne 0) { throw "AML tracking failed for C=$c" }
}
.\.venv\Scripts\python.exe .\compare.py
.\.venv\Scripts\python.exe .\inspect_run.py
```

이 단계의 학습은 로컬에서 실행하며 AML 클러스터는 쓰지 않는다. Studio Jobs에서 파라미터, 메트릭, 파일, 모델을 확인한다.

AML workspace는 MLflow 호환 API를 제공하므로 별도 MLflow 서버 VM은 필요하지 않다.

URI 변경은 로컬 run과 모델을 이전하지 않는다. 코드를 재실행해 AML run을 만들고, `compare.py`로 AML의 run ID를 선택한다.

Tracking과 Registry는 같은 workspace를 사용한다. 로컬 `runs:/...` URI를 AML Registry에 바로 넘기지 않는다.

## 학습 실행 위치를 AML Job으로 변경

이 단계는 기존 AML CPU compute cluster를 사용한다. 아래의 `cpu-cluster`는 실제 이름으로 바꾼다. 클러스터가 없다면 [compute cluster 만들기](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-attach-compute-cluster?view=azureml-api-2)를 준비 작업으로 둔다.

원격 학습에는 compute가 사용된다. 리전 SKU, quota, 최소, 최대 노드 수, 유휴 축소 설정을 확인한다.

### 실행 환경

`conda.yml`:

```yaml
name: mlflow-wine-study
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - pip:
      - mlflow==2.16.2
      - azureml-mlflow==1.62.0.post6
      - scikit-learn==1.5.1
      - pandas==2.2.3
      - numpy==1.26.4
      - sqlalchemy==2.0.43
```

로컬 플러그인은 Job 컨테이너에 자동 포함되지 않으므로 원격 환경에도 `azureml-mlflow` 등 의존성을 설치한다.

### Job 정의

`job.yml`:

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json
type: command
display_name: mlflow-wine-study
experiment_name: mlflow-wine-study
code: ./src
command: python train.py --C ${{inputs.c}}
inputs:
  c: 0.1
environment:
  image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
  conda_file: ./conda.yml
compute: azureml:cpu-cluster
limits:
  timeout: 1800
tags:
  study: mlflow-aml
```

`code`는 `src`만 지정한다. 폴더 전체를 올리면 가상환경, 로컬 DB, 인증 파일까지 전송될 수 있다.

학습 코드에 Tracking URI나 `set_experiment()`를 추가하지 않는다. AML Job에서는 실행하는 workspace가 추적 대상으로 설정되고, `experiment_name`과 `display_name`은 Job 정의에서 정한다. `start_run()`에 별도의 `run_name`도 전달하지 않는다.

공식 실행 추적 문서는 AML Job에서 `start_run()`을 명시적으로 쓰더라도 해당 Job의 실행 문맥을 재사용할 수 있다고 설명한다. 로컬 코드를 옮긴다는 이유로 새 run을 중첩해서 만들거나, 로컬 SQLite URI를 Job 환경에 넣지 않는다.

이 YAML은 학습용 설정 예시이며 베이스 이미지의 `latest` 태그는 나중에 바뀔 수 있다. 같은 환경을 고정해 운영하는 단계에서는 이미지 digest와 등록된 AML Environment의 버전도 관리할 대상이다.

### Job 제출과 결과 확인

앞의 연결 설정과 같은 PowerShell 세션에서 실행한다. 다른 터미널이라면 subscription, resource group, workspace 변수를 다시 설정한다.

```powershell
$jobNames = foreach ($c in @("0.01", "0.1", "1.0")) {
    $name = az ml job create --file .\job.yml --resource-group $resourceGroup --workspace-name $workspace --subscription $subscription --set "inputs.c=$c" --query name --output tsv
    if ($LASTEXITCODE -ne 0) { throw "Job submission failed for C=$c" }
    $name
}

foreach ($name in $jobNames) {
    az ml job stream --name $name --resource-group $resourceGroup --workspace-name $workspace --subscription $subscription
}
```

제출 성공은 학습 완료를 뜻하지 않는다. Studio나 CLI에서 `Completed`를 확인하고, 실패 시 로그를 조사한다.

```powershell
foreach ($name in $jobNames) {
    az ml job show --name $name --resource-group $resourceGroup --workspace-name $workspace --subscription $subscription --query status --output tsv
}
```

완료 후에는 로컬에서 같은 `compare.py`로 AML 쪽 결과를 조회할 수 있다. 앞의 로컬 학습과 같은 experiment를 사용하므로 그 실행도 비교 대상에 포함된다.

```powershell
.\.venv\Scripts\python.exe .\compare.py
.\.venv\Scripts\python.exe .\inspect_run.py
```

여기서는 AML CLI v2 command Job을 사용한다. [공식 개요](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow?view=azureml-api-2#training-with-mlflow-projects-preview)는 `MLproject` 제출 경로가 2026년 9월 종료되고 Jobs로 전환된다고 안내한다. MLflow Tracking 종료를 뜻하지 않는다.

## 확인할 결과

로컬 학습 run은 AML experiment에, 원격 Job은 `Completed` 상태와 모델, 메트릭을 같은 workspace에 남겨야 한다. AML에서 `compare.py`를 다시 실행하면 선택 파일도 AML URI와 run ID를 가리킨다.

## 오류 확인

| 증상 | 확인할 부분 |
| --- | --- |
| `azureml://` 처리 오류 | 실제 실행 환경에 `azureml-mlflow`가 설치되었는지 |
| 401 또는 403 | 로그인한 tenant와 subscription, workspace의 작업 권한 |
| 시간 초과나 이름 확인 오류 | workspace와 스토리지 접근, Private Link와 DNS |
| 메트릭은 있지만 모델 파일 기록 실패 | 고정한 패키지 버전과 아티팩트 접근 |
| Job 제출 후 대기 또는 실패 | compute, 할당량, 환경 빌드, 실제 Job 로그 |
| 기대한 설정이 Job에 없음 | YAML inputs와 command, 업로드한 `src` 내용 |

## 비용과 생각할 점

Job 완료 후에도 compute의 최소 노드 수와 축소 설정을 확인한다. 공유 리소스는 삭제하지 않는다.

- UI에 Job이 보이는 것만으로 학습 실행 위치를 알 수 있는가.
- 기록 대상만 바꾼 실행과 컨테이너에서 실행한 Job은 어떤 증거가 다른가.
- 제출 성공과 학습 완료를 각각 어디에서 확인해야 하는가.

## 참고 자료

- [MLflow 연결 설정](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-configure-tracking?view=azureml-api-2)
- [실험과 실행 추적](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-cli-runs?view=azureml-api-2)
- [Workspace 권한](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-assign-roles?view=azureml-api-2)
- [Workspace 준비](https://learn.microsoft.com/en-us/azure/machine-learning/quickstart-create-resources?view=azureml-api-2)
- [Compute cluster 준비](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-attach-compute-cluster?view=azureml-api-2)
- [Command Job YAML](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-command?view=azureml-api-2)

[이전: 03. 모델 형식과 재사용](/docs/tech/ops/mlops/labs/03-model-format-and-loading/), [시리즈 목차](/docs/tech/ops/mlops/labs/), [다음: 05. 모델 등록과 버전 관리](/docs/tech/ops/mlops/labs/05-model-registration/)
