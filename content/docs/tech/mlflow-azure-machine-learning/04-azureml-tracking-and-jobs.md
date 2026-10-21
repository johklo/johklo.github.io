---
title: "04. AML 연결과 원격 학습 Job"
description: "로컬 코드를 AML에 연결해 기록한 뒤 같은 학습을 원격 command Job으로 실행하기"
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 40
tags: ["mlflow", "mlops", "azure-machine-learning"]
---

AML 연결을 기록 대상의 변경과 학습 실행 위치의 변경으로 나눴다. 로컬에서 학습하고 AML에 기록하는 단계부터 확인한 뒤, 같은 코드를 원격 Job으로 제출한다.

## 준비 조건

01~03편의 실습 폴더, `train.py`, `compare.py`, `inspect_run.py`를 유지한다. AML workspace에 접근할 계정과 네트워크가 필요하다. 원격 Job에는 CPU compute cluster도 필요하다. 이 편은 실행 결과를 기록하고 선택하는 단계이며 모델 등록은 [05편](../05-model-registration/)에서 진행한다.

## 로컬 학습의 기록 위치를 AML로 변경

여기부터는 AML workspace가 필요하다. workspace가 없다면 [초기 리소스 만들기](https://learn.microsoft.com/en-us/azure/machine-learning/quickstart-create-resources?view=azureml-api-2)를 별도의 준비 작업으로 둔다. workspace의 생성과 사용에는 연결된 스토리지 등의 비용도 관계된다.

### 인증과 권한

AML 연결에 필요한 플러그인은 원격 기록 단계에서 설치한다.

`requirements-azure.txt`:

```text
-r requirements.txt
azureml-mlflow==1.62.0.post6
```

로컬 실행은 Azure CLI에 로그인한 사용자로 인증한다. 이 편에서는 workspace의 실험과 Job을 다룰 권한이 필요하다. 05편에서 모델 등록까지 진행하려면 모델 생성과 갱신 권한도 별도로 확인한다. workspace 범위의 `AzureML Data Scientist` 역할이 학습용 권한의 한 예다. 실제 부여는 조직의 권한 관리에 맞춘다.

[Workspace 권한 문서](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-assign-roles?view=azureml-api-2#mlflow-operations)는 실험과 Job, 모델 조회, 모델 생성 및 갱신의 권한을 나누어 설명한다. 기록 권한만 있어도 모델 등록까지 가능한 것으로 보지 않는다. 또한 `AzureML Data Scientist`는 compute 생성과 삭제를 포함하지 않으므로, 새 클러스터가 필요하면 그 준비 권한도 별도로 확인한다.

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

이 로그인은 직접 실행하는 학습용 절차다. 무인 CI에 사용자의 브라우저 인증을 가져가는 방식은 아니다. 자동화할 때의 인증과 권한은 별도로 설계하고, 비밀 정보를 학습 코드나 Job YAML에 넣지 않는다.

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

Tracking URI는 CLI가 반환한 값을 그대로 쓴다. 리전 이름 등으로 직접 조립하지 않는다. Private Link를 사용하는 workspace에서는 클라이언트의 네트워크 접근 경로와 이름 확인도 필요하다.

Tracking URI를 설정한 것만으로 인증과 통신이 확인되지는 않는다. 실제 experiment 조회나 run 시작처럼 서비스에 접근하는 작업에서 연결이 확인된다.

[연결 설정 문서](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-configure-tracking?view=azureml-api-2)의 인증은 실행 환경에 따라 Azure CLI 로그인, 환경 자격 증명, 관리 ID 등 사용 가능한 방식을 이용한다. 이 로컬 실습은 CLI 로그인을 사용한다. URI에 사용자 비밀이나 토큰을 붙여 인증하는 구조로 이해하지 않는다.

### 같은 코드로 재실행

```powershell
foreach ($c in @("0.01", "0.1", "1.0")) {
    .\.venv\Scripts\python.exe .\src\train.py --C $c
    if ($LASTEXITCODE -ne 0) { throw "AML tracking failed for C=$c" }
}
.\.venv\Scripts\python.exe .\compare.py
.\.venv\Scripts\python.exe .\inspect_run.py
```

학습은 계속 로컬 PC에서 실행된다. AML 학습 클러스터를 사용한 것은 아니다. Azure Machine Learning studio의 Jobs에서 experiment를 열어 파라미터, 메트릭, 파일과 모델을 확인한다.

AML workspace는 MLflow 호환 API를 제공한다. workspace 안에 MLflow 서버용 VM을 직접 만드는 절차가 아니다.

URI를 바꾸는 것만으로 기존 로컬 run과 모델이 이전되지는 않는다. 여기서는 같은 코드를 다시 실행해 AML에 새 run을 만든다. `compare.py`를 다시 실행하는 이유도 AML 쪽의 run ID를 선택하기 위해서다.

이 실습에서는 Tracking과 Registry를 같은 workspace에 맞췄다. 로컬의 `runs:/...`를 그대로 AML Registry에 넘기는 방식이 아니다.

## 학습 실행 위치를 AML Job으로 변경

이 단계는 기존 AML CPU compute cluster를 사용한다. 아래의 `cpu-cluster`는 실제 이름으로 바꾼다. 클러스터가 없다면 [compute cluster 만들기](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-attach-compute-cluster?view=azureml-api-2)를 준비 작업으로 둔다.

학습용이라도 리전의 SKU와 할당량, 최소 노드 수, 최대 노드 수, 유휴 시 축소 설정을 확인한다. 로컬에서 원격 기록만 보내던 단계와 달리, 여기부터는 원격 학습용 컴퓨팅도 사용한다.

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

로컬에 설치한 플러그인이 Job 컨테이너에도 있는 것은 아니다. 원격 환경에도 `azureml-mlflow`와 같은 학습 의존성을 포함한다.

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

`code`는 `src`만 지정했다. 실습 폴더 전체를 올리면 가상환경, 로컬 DB, 인증용 파일이 함께 전송될 수 있다.

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

Job 제출 성공과 학습 완료는 다른 상태다. studio 또는 아래 명령으로 각 Job이 `Completed`인지 확인한다. 실패했다면 비교로 넘어가기 전에 로그에서 원인을 확인한다.

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

이 실습은 AML CLI v2의 command Job을 사용한다. `MLproject` 파일을 이용한 AML 학습 제출 경로와는 구분했다. [공식 MLflow 개요](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow?view=azureml-api-2#training-with-mlflow-projects-preview)에는 해당 경로의 2026년 9월 종료와 Jobs로의 전환이 안내되어 있다. MLflow Tracking 자체가 종료된다는 뜻은 아니다.

## 확인할 결과

원격 기록 단계에서는 로컬에서 학습한 run이 AML Jobs의 experiment에 나타나야 한다. 원격 Job 단계에서는 제출한 작업의 상태가 `Completed`이고 모델과 메트릭이 같은 workspace에 남아야 한다. `compare.py`를 AML 대상으로 다시 실행하면 선택 파일의 Tracking URI와 run ID도 AML 기록으로 바뀐다.

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

[이전: 03. 모델 형식과 재사용](../03-model-format-and-loading/), [시리즈 목차](../), [다음: 05. 모델 등록과 버전 관리](../05-model-registration/)
