---
title: "책 1~13장 순차 실습 가이드"
description: "준비 사항부터 클러스터 파이프라인, 서빙, 모니터링, RAG 출시 복구까지 실제 실행 출력과 화면으로 따라가는 ML 플랫폼 로컬 실행판"
date: 2026-11-07T14:00:00+09:00
weight: 140
aliases:
  - /docs/tech/ops/mlops/labs/book-01-13-guide/
tags: ["mlops", "ml-platform-engineering", "hands-on", "llmops"]
---

책의 개념을 이해하는 [챕터 해설](/docs/tech/machine-learning-platform-engineering/00-overview/)과 직접 실행하는 과정은 분리했다. 이 가이드는 『Machine Learning Platform Engineering』의 1~13장 순서로 환경, 데이터, 모델, 서비스와 변경 평가를 연결한다. 각 단계는 목적, 사용할 터미널과 폴더, 입력할 명령, 실제로 관찰한 출력, 화면과 완료 확인 항목으로 이루어진다. 앞 단계가 남긴 파일을 다음 단계가 그대로 입력으로 쓰므로 순서를 건너뛰지 않는다.

**현재 판은 독립 실습 저장소 [ml-platform-engineering-labs](https://github.com/johklo/ml-platform-engineering-labs)의 고정 커밋 `ff23b38f88d88268216e2985ff5b6ed0c3defb8c`를 기반으로 한 로컬 실행판이며, 책의 모든 도구와 원본 실습을 재현한 완성판은 아니다.** 2026년 11월 7일 Windows 11, Docker Desktop 4.67.0, kind `book-env` 클러스터에서 이 문서의 명령을 위에서 아래로 새 작업 폴더에 다시 실행했다. 본문의 출력과 화면은 모두 그 실행에서 가져왔다. 외부 유료 LLM, DeepEval과 Langfuse 연결은 실행하지 않았다. 무엇을 실행했고 무엇이 남았는지는 [구현과 검증 범위](#verification-scope)에 정리했다.

출력에 나오는 개인 경로는 `C:\Users\<사용자>\...` 또는 `...\`로 줄였다. 실행 ID, 해시, 점수는 실행마다 달라질 수 있다. 같은 형식과 같은 판정이 나오면 정상이다.

## 준비사항 {#prerequisites}

아래 항목을 위에서부터 설치하고 각 확인 명령의 출력이 비슷하게 나오는지 본다. 모든 명령은 Windows PowerShell 7 기준이다. 설치 뒤에는 새 PowerShell 창을 열어야 PATH가 반영된다.

| 항목 | 필요한 구간 | 설치 | 확인 |
| --- | --- | --- | --- |
| Git | 전체 | `winget install --id Git.Git -e` | `git --version` |
| uv | 전체 | `winget install --id astral-sh.uv -e` | `uv --version` |
| Python 3.12 | 전체 | `uv python install 3.12` | `uv python find 3.12` |
| Docker Desktop (Linux 엔진) | 3장, 5장 | `winget install --id Docker.DockerDesktop -e` | `docker version` |
| kind v0.27.0 | 3장, 5장 | 아래 다운로드 명령 | `kind version` |
| kubectl | 3장, 5장 | Docker Desktop에 포함, 또는 `winget install --id Kubernetes.kubectl -e` | `kubectl version --client` |
| Node.js LTS | 13장 Promptfoo | `winget install --id OpenJS.NodeJS.LTS -e` | `node --version` |

winget은 각 도구의 최신판을 설치한다. 2026년 11월 기준 winget 최신판은 uv 0.13.7, Docker Desktop 4.98.0, Node.js 26.13.0으로 이번 검증에 쓴 버전(uv 0.12.3, Docker Desktop 4.67.0, Node.js 24.12.0)보다 새롭다. 의존성은 `uv.lock`과 `promptfoo@0.125.0`으로 고정되므로 그대로 진행하고, 출력 형식이 다르면 아래 실제 출력의 판정 값(통과 여부, 종료 코드, 개수)을 기준으로 비교한다.

### 0-1. Git과 uv를 확인한다

**터미널 A, 아무 폴더.** Git은 실습 코드를 고정 커밋으로 받고, uv는 Python과 가상환경을 잠금 파일 그대로 설치한다.

```powershell
git --version
uv --version
```

실제 출력:

```text
git version 2.47.1.windows.1
uv 0.12.3 (507230998 2026-08-07 x86_64-pc-windows-msvc)
```

winget을 쓸 수 없는 환경이라면 uv는 `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`로 설치한다.

### 0-2. Python 3.12를 uv로 설치한다

**터미널 A, 홈 폴더.** 실습 저장소는 `>=3.11,<3.13`만 허용한다. 시스템에 깔린 다른 Python이나 Conda 환경을 쓰지 않고 uv가 관리하는 3.12를 사용한다. 3.13 이상으로 의존성 오류를 우회하지 않는다.

```powershell
Set-Location $HOME
uv python install 3.12
uv python find 3.12
```

실제 출력(마지막 줄):

```text
C:\Users\<사용자>\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe
```

### 0-3. Docker Desktop의 Linux 엔진을 켠다

**터미널 A.** 3장과 5장에서 kind 클러스터와 파이프라인 이미지를 만든다. Docker Desktop 설정의 Resources에서 메모리를 8GB 이상 할당하고, WSL 2 기반 엔진을 사용한다. 트레이 아이콘이 `Engine running`이 될 때까지 기다린다.

```powershell
docker version --format "Client {{.Client.Version}} / Server {{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}"
docker info --format "{{.OSType}} {{.NCPU}} CPU"
```

실제 출력:

```text
Client 29.3.1 / Server 29.3.1 linux/amd64
linux 16 CPU
```

`Server` 정보 없이 `dockerDesktopLinuxEngine` 연결 오류가 나오면 엔진이 꺼진 상태다. 이 상태에서는 3장과 5장의 클러스터 단계로 넘어가지 않는다.

### 0-4. kind와 kubectl을 준비한다

**터미널 A.** 실습 클러스터 저장소는 kind v0.27.0으로 확인했다. 다른 버전을 쓰면 노드 이미지와 설치 스크립트가 맞지 않을 수 있다.

```powershell
New-Item -ItemType Directory -Path "$HOME\bin" -Force | Out-Null
curl.exe -Lo "$HOME\bin\kind.exe" https://kind.sigs.k8s.io/dl/v0.27.0/kind-windows-amd64
$env:PATH = "$HOME\bin;$env:PATH"
kind version
kubectl version --client
```

실제 출력:

```text
kind v0.27.0 go1.23.6 windows/amd64
Client Version: v1.34.1
Kustomize Version: v5.7.1
```

`$HOME\bin`은 Windows 환경 변수 설정에서 사용자 PATH에 추가해 두면 새 터미널마다 다시 지정하지 않아도 된다. kubectl은 Docker Desktop 설치 폴더(`C:\Program Files\Docker\Docker\resources\bin`)에 함께 들어 있다.

### 0-5. Node.js를 확인한다

**터미널 A.** 13장의 Promptfoo만 Node.js를 사용한다. 패키지는 실행할 때 `npm exec`로 받으므로 전역 설치하지 않는다.

```powershell
node --version
npm --version
```

실제 출력:

```text
v24.12.0
11.6.2
```

### 0-6. 디스크, 메모리, 네트워크와 시간을 확보한다

| 항목 | 이번 실행에서 관찰한 값 | 권장 |
| --- | --- | --- |
| 가상환경 4개 | base 0.55GB, tools 0.72GB, bento 0.58GB, vision 1.75GB | uv 캐시를 포함해 10GB 여유 |
| 실습 이미지 `book-labs:ff23b38` | 디스크 1.14GB, 내용 254MB | Docker 디스크 여유 5GB |
| kind `book-env` 클러스터 | KFP, MinIO, MySQL, PostgreSQL, Redis, MLflow | Docker 메모리 8GB, 디스크 40GB |
| 메모리 | 64GB 노트북에서 실행 | 16GB 이상 |
| 시간 | uv 동기화 환경당 10~30초(캐시 있음), 이미지 빌드 약 3분, KFP 실행 약 2분, YOLO 10 epoch 41초(i7-1360P CPU) | 처음 설치는 패키지 다운로드로 수십 분 |

네트워크는 PyPI, GitHub, `docker.io`, `ghcr.io`, Ultralytics 자산(`yolov8n.pt`, `Arial.ttf`), GroupLens와 npm 레지스트리에 접근한다. `docker.io`에서 TLS 시간 초과가 나면 같은 명령을 다시 실행한다. 회사 프록시 아래에서는 `HTTPS_PROXY`를 먼저 설정한다.

### 0-7. 선택 자격 증명은 지금 준비하지 않는다

Azure OpenAI, Gemini 같은 외부 생성 모델, DeepEval의 판정 모델과 Langfuse 키는 이 가이드의 기본 경로에 필요하지 않다. 이 판에서는 실행하지 않았다. 나중에 연결할 때도 키를 저장소나 명령 기록에 남기지 않고 현재 터미널의 환경 변수로만 넘긴다.

**완료 확인**

- [ ] `git`, `uv`, `kind`, `kubectl`, `node`가 버전을 출력한다.
- [ ] `uv python find 3.12`가 uv 관리 인터프리터를 가리킨다.
- [ ] `docker version`에 `Server ... linux/amd64`가 나온다.
- [ ] 디스크 여유가 50GB 이상이다(클러스터 포함).

## 진행 지도 {#roadmap}

터미널은 세 종류로 구분한다. **A 작업 터미널**은 명령을 입력하고 결과를 확인한다. **B 서버 터미널**은 API, UI, 포트포워딩처럼 켜 두는 프로세스를 실행하며, 단계가 끝나면 그 창에서 `Ctrl+C`로 종료한다. **C 브라우저**는 화면을 확인한다. 모든 서버는 `127.0.0.1`에만 연다.

| 단계 | 장 | 터미널 | 입력 | 산출물 | 확인 방법 |
| --- | --- | --- | --- | --- | --- |
| 0 | 준비 | A | 설치 명령 | 도구와 Python 3.12 | 각 `--version` |
| 1 | 1장 | A | 저장소 고정 커밋 | `book-env-base` 환경 | `ml-labs --help` |
| 2 | 2장 | A | 없음 | `smoke` 후보 3개와 보고서 | `registered` 3개 |
| 3 | 3장 | A, B(포트포워딩), C | `ml-platform-book-env` | kind `book-env`, 8080/5000/8888 | `bookenv.py status`, KFP 화면 |
| 4 | 4장 | A, B(MLflow 5001), C | 합성 평점 | `models:/book-movie/1`, Feast 저장소 | MLflow 화면, 온라인 조회 |
| 5 | 5장 | A, C | 4장 코드 | 파이프라인 YAML, `book-labs:ff23b38`, KFP run | KFP 그래프 3개 작업 성공 |
| 6 | 6장 | A, B(8000, 3000), C | 4장 후보 | FastAPI 응답, Bento | Swagger 응답 |
| 7 | 7장 | A | 합성 카드, MovieLens zip | 카드 데이터, MovieLens 변환 | `manifest.json` |
| 8 | 8장 | A, C | 카드 데이터 | 색상 기준선, YOLO `best.pt`, 등록 | `results.png`, MLflow |
| 9 | 9장 | A, C | 새 seed 평점 | 선택 후보, `book-movie-selected` | 선택 표, MLflow |
| 10 | 10장 | A, B(8000, 8002), C | 선택 후보, YOLO 후보 | 출시 기록, 배치 결과 | `release_id`, `reused`, `backend` |
| 11 | 11장 | A, C | 10장 서버, 평점 | `/metrics`, `drift.html`, 통합 증거 | 카운터, 보고서, `evidence.json` |
| 12 | 12장 | A | 데모 문서 | RAG v1 후보와 출시 저장소 | 인용과 `no_grounding` |
| 13 | 13장 | A, B(8003), C | v1 후보 | 거절된 후보, v2, 복구, Promptfoo | HTTP `release_id` 비교, 3 passed |

### 새 터미널마다 붙여 넣는 머리말

PowerShell 변수와 환경 변수는 창마다 따로다. A나 B 터미널을 새로 열 때마다 아래를 먼저 실행하고, 각 단계가 지정한 `UV_PROJECT_ENVIRONMENT`로 바꾼다.

```powershell
Set-Location $HOME\ml-labs-book\ml-platform-engineering-labs
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
Remove-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue
```

`MLFLOW_TRACKING_URI`를 지우는 이유는 다른 프로젝트에서 설정한 원격 MLflow로 이 실습 기록이 섞여 들어가지 않게 하기 위해서다. 각 명령은 실습 코드가 지정하는 로컬 SQLite Tracking DB를 사용한다.

### 환경을 네 개로 나눈다

책의 원본 경로와 독립 구현의 의존성은 다르다. 책 4~5장의 서버용 MLflow 3.0.0과 이 가이드의 MLflow 2.16.2를 같은 환경에 섞지 않는다. 같은 소스와 `uv.lock`에서 extra만 달리해 네 환경을 만든다. `uv sync --all-extras`는 extra 사이의 충돌 때문에 지원하지 않는다.

| 환경 경로 | 사용하는 장 | 설치할 extra |
| --- | --- | --- |
| `.ml-labs\book-env-base` | 1, 2, 4, 6, 7, 9, 10, 12, 13장 | `dev` |
| `.ml-labs\book-env-tools` | 4장 Feast, 5장 KFP, 11장 Evidently | `dev`, `feast`, `pipeline`, `monitor` |
| `.ml-labs\book-env-bento` | 6장 BentoML | `dev`, `bento` |
| `.ml-labs\book-env-vision` | 8장, 10장 YOLO | `dev`, `vision` |

## 1장. 환경과 실행 출처를 준비한다 {#chapter-01}

먼저 설치한 Python과 내려받은 코드가 무엇인지 고정한다. 아직 GPU나 클라우드 계정은 필요하지 않다.

### 1-1. 실습 저장소를 고정 커밋으로 받는다

**터미널 A, 홈 폴더.** 이 가이드의 명령은 아래 커밋으로 대조했다. 최신 `main`을 받으면 명령이나 출력이 달라질 수 있다.

```powershell
New-Item -ItemType Directory -Path "$HOME\ml-labs-book" -Force | Out-Null
Set-Location "$HOME\ml-labs-book"
git clone https://github.com/johklo/ml-platform-engineering-labs.git
Set-Location ml-platform-engineering-labs
git checkout --detach ff23b38f88d88268216e2985ff5b6ed0c3defb8c
git rev-parse HEAD
```

실제 출력(마지막 줄):

```text
ff23b38f88d88268216e2985ff5b6ed0c3defb8c
```

이후 코드를 수정하려면 별도 브랜치를 만들고 변경 커밋을 기록한다. 수정한 코드로 얻은 결과를 원래 커밋의 결과라고 표시하지 않는다.

### 1-2. 기본 환경을 만든다

**터미널 A, `ml-platform-engineering-labs`.** 기본 환경은 데이터 준비, 추천, API와 로컬 RAG에 쓴다. `--locked`는 `uv.lock`과 다른 버전을 설치하지 못하게 막는다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
Remove-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue
uv sync --locked --python 3.12 --extra dev
uv run --locked --extra dev python --version
uv run --locked --extra dev ml-labs --help
```

실제 출력(캐시가 있는 상태에서 다시 실행):

```text
Resolved 367 packages in 2ms
Checked 86 packages in 33ms
Python 3.12.12
usage: ml-labs [-h]
               {cards,movies,rag,register,serve,smoke,release,batch,exercise,azure,tools}
               ...

Run reproducible local ML platform labs; cloud resources are never created.
```

처음 실행하면 패키지를 내려받아 설치하는 줄이 추가로 나온다. `ml-labs`를 찾지 못하면 `UV_PROJECT_ENVIRONMENT`를 지정한 같은 터미널인지 확인한다.

### 1-3. 나머지 세 환경을 미리 만든다

**터미널 A, 같은 폴더.** 장마다 환경을 바꿔 쓰므로 한 번에 만들어 둔다. 각 명령은 해당 환경만 만들고, 마지막에 기본 환경으로 돌아온다.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-tools"
uv sync --locked --python 3.12 --extra dev --extra feast --extra pipeline --extra monitor
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-bento"
uv sync --locked --python 3.12 --extra dev --extra bento
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-vision"
uv sync --locked --python 3.12 --extra dev --extra vision
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
Get-ChildItem .ml-labs -Directory -Filter "book-env-*" | Select-Object Name
```

실제 출력(마지막 명령):

```text
Name
----
book-env-base
book-env-bento
book-env-tools
book-env-vision
```

이번 실행에서 uv 캐시가 있는 상태의 동기화는 base 11초, tools 13초, bento 12초, vision 29초가 걸렸다. vision 환경은 PyTorch CPU 빌드를 받으므로 처음에는 가장 오래 걸린다.

**완료 확인**

- [ ] `git rev-parse HEAD`가 `ff23b38f...`다.
- [ ] `python --version`이 `Python 3.12.x`다.
- [ ] `.ml-labs` 아래에 `book-env-*` 폴더가 네 개 있다.

## 2장. 생애주기를 작은 실행으로 확인한다 {#chapter-02}

도구를 하나씩 익히기 전에 데이터 준비, 후보 생성, 평가와 등록이 한 번에 이어지는지 확인한다.

### 2-1. 세 프로젝트를 한 번에 실행한다

**터미널 A, 기본 환경.** `smoke`는 카드 탐지 기준선, 영화 추천과 문서 검색을 각각 준비, 학습, 평가, 등록한다. 결과는 `$W\smoke` 아래에만 쓴다.

```powershell
uv run --locked --extra dev ml-labs smoke --work "$W\smoke"
```

실제 출력(마이그레이션 로그를 줄이고 앞뒤만 남김):

```text
2026/11/07 20:26:56 INFO mlflow.store.db.utils: Creating initial MLflow database tables...
2026/11/07 20:26:57 INFO mlflow.tracking.fluent: Experiment with name 'ml-platform-labs' does not exist. Creating a new experiment.
Successfully registered model 'ml-labs-cards'.
Created version '1' of model 'ml-labs-cards'.
Successfully registered model 'ml-labs-movies'.
Created version '1' of model 'ml-labs-movies'.
Successfully registered model 'ml-labs-rag'.
Created version '1' of model 'ml-labs-rag'.
{
  "cards": { "task": "cards", "passed": true, ... },
  "movies": { "task": "movies", "passed": true, ... },
  "rag": { "task": "rag", "passed": true, "answer_mode": "extractive_offline", ... },
  "registered": [
    "models:/ml-labs-cards/1",
    "models:/ml-labs-movies/1",
    "models:/ml-labs-rag/1"
  ]
}
```

`Failed to resolve installed pip version` 경고는 uv 환경에 pip가 없어서 나오는 MLflow 경고이며 결과에 영향이 없다.

### 2-2. 후보 명세와 평가 보고서를 읽는다

**터미널 A.** `candidate.json`은 모델 파일이 아니라 원천 run, 모델 URI와 데이터 지문을 연결한 명세다. 평가 보고서는 그 후보에 묶인다.

```powershell
Get-Content "$W\smoke\runs\movies\candidate.json"
Get-ChildItem "$W\smoke" | Select-Object Name
```

실제 출력(일부):

```text
{
  "task": "movies",
  "run_id": "16fefc79d7094604876f9e5a36d8c924",
  "model_uri": "runs:/16fefc79d7094604876f9e5a36d8c924/model",
  "tracking_uri": "sqlite:///C:/Users/<사용자>/.../.ml-labs/book-01/smoke/tracking/tracking.db",
  "dataset": {
    "dataset": "synthetic-movies",
    "seed": 42,
    "rows": 432,
    "sha256": "6bb44545d72777952854f09ac4c22213a63fc8098cf9f664e690efce5e374910",
    ...
  },
  "metrics": {
    "validation_rmse": 0.4885255171433486,
    "baseline_rmse": 0.730372280846849,
    ...
  },
  "registered_model": "ml-labs-movies",
  "registered_version": "1",
  "registered_alias": "champion",
  "registered_uri": "models:/ml-labs-movies/1"
}

Name
----
data
reports
runs
tracking
```

`registered_uri`는 `models:/이름/숫자`처럼 구체 버전을 포함해야 한다. 별칭 `champion`만 기록하면 나중에 어떤 버전이었는지 다시 찾을 수 없다.

이 실행의 카드는 색상 규칙 기준선이고 문서 응답은 검색 문장 인용이다. 여기서 세 프로젝트가 성공해도 YOLO 학습이나 LLM 생성이 완료된 것은 아니다.

**완료 확인**

- [ ] `registered`에 세 모델 URI가 나온다.
- [ ] `$W\smoke`에 `data`, `reports`, `runs`, `tracking`이 생겼다.
- [ ] 기존 데이터가 있는 폴더라는 오류가 나오면 지우지 않고 `$W = ".ml-labs\book-02"`처럼 새 폴더로 다시 시작한다.

## 3장. 로컬 실행과 클러스터 실행을 구분한다 {#chapter-03}

컨테이너와 Kubernetes는 Python 설치에 포함되지 않는다. 이 장에서는 책 4~5장의 플랫폼(KFP, S3 호환 저장소, MLflow, Redis)을 kind 클러스터 `book-env`에 올리고 5장에서 쓸 접속을 연다. 전체 Kubeflow와 Notebooks를 설치하는 과정은 아니다.

### 3-1. 엔진과 클라이언트를 확인한다

**터미널 A.** 0-3, 0-4에서 확인한 도구를 클러스터 작업 직전에 다시 확인한다. 엔진이 중간에 멈추면 이미지 빌드와 KFP 실행이 모두 실패한다.

```powershell
docker version --format "Client {{.Client.Version}} / Server {{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}"
kind version
kubectl version --client
```

실제 출력:

```text
Client 29.3.1 / Server 29.3.1 linux/amd64
kind v0.27.0 go1.23.6 windows/amd64
Client Version: v1.34.1
Kustomize Version: v5.7.1
```

### 3-2. 클러스터 저장소를 받고 사전 점검한다

**터미널 A, `$HOME\ml-labs-book`.** 클러스터 설치 스크립트는 별도 저장소 [ml-platform-book-env](https://github.com/johklo/ml-platform-book-env)에 있다. 표준 라이브러리만 쓰므로 uv의 Python 3.12로 바로 실행한다.

```powershell
Set-Location "$HOME\ml-labs-book"
git clone https://github.com/johklo/ml-platform-book-env.git
Set-Location ml-platform-book-env
uv run --no-project --python 3.12 python bookenv.py check
```

실제 출력:

```text
docker   C:\Program Files\Docker\Docker\resources\bin\docker.EXE
kind     C:\Users\<사용자>\...\bin\kind.EXE
kubectl  C:\Program Files\Docker\Docker\resources\bin\kubectl.EXE
git      C:\Program Files\Git\cmd\git.EXE
$ C:\Program Files\Docker\Docker\resources\bin\docker.EXE info --format Docker {{.ServerVersion}}
Docker 29.3.1
All required tools are available.
```

### 3-3. 클러스터를 만든다

**터미널 A, `ml-platform-book-env`.** kind 클러스터를 만들고 KFP standalone 2.4.1, S3 호환 저장소, PostgreSQL, Redis와 MLflow를 설치한다. 이미지가 캐시돼 있으면 8분 정도, 처음이면 20분 넘게 걸린다.

```powershell
uv run --no-project --python 3.12 python bookenv.py up
```

`The environment is ready. Next: python bookenv.py forward`가 나오면 끝난 것이다. 설치 중 `metadata-grpc-deployment`, `ml-pipeline`이 몇 번 재시작하는 것은 MySQL이 늦게 뜨면서 생기는 정상 동작이다. 시간 초과가 나면 같은 명령을 다시 실행해 기존 클러스터에서 이어서 설치한다. 이번 검증은 같은 스크립트로 미리 만들어 둔 `book-env` 클러스터를 재사용했으므로 `up`을 새로 실행하지 않았다.

### 3-4. 포트포워딩을 켜 둔다

**터미널 B, `ml-platform-book-env`.** 클러스터 서비스를 로컬 포트로 연다. 이 창은 5장이 끝날 때까지 닫지 않는다. Pod가 재시작되면 스크립트가 터널을 다시 연다.

```powershell
Set-Location "$HOME\ml-labs-book\ml-platform-book-env"
uv run --no-project --python 3.12 python bookenv.py forward
```

| 주소 | 서비스 |
| --- | --- |
| `http://127.0.0.1:8080` | KFP UI와 API |
| `http://127.0.0.1:5000` | 책 실습용 클러스터 MLflow 3.0.0 |
| `http://127.0.0.1:8888/buckets/` | S3 호환 저장소 화면 |
| `127.0.0.1:9000`, `127.0.0.1:6379` | S3 API, Redis |

5000번은 클러스터 MLflow가 쓰므로 4장의 로컬 MLflow UI는 5001번에서 연다.

### 3-5. Pod 상태와 KFP 화면을 확인한다

**터미널 A, `ml-platform-book-env`.** 클러스터가 만들어진 상태와 플랫폼 Pod가 요청을 받을 수 있는 상태는 다르다.

```powershell
uv run --no-project --python 3.12 python bookenv.py status
```

실제 출력(다른 실습이 남긴 완료 Pod는 생략):

```text
== kubeflow
NAME                                                READY   STATUS      RESTARTS      AGE
cache-deployer-deployment-67b7ff8785-jvwl9          1/1     Running     0             89m
cache-server-fb5bc88b7-cjz89                        1/1     Running     0             89m
metadata-envoy-deployment-7964b7b586-9nmcn          1/1     Running     0             89m
metadata-grpc-deployment-66b7d897b4-xt9b9           1/1     Running     7 (82m ago)   89m
metadata-writer-76899549df-bqvxx                    1/1     Running     3 (78m ago)   89m
minio-76d4b8f979-bzk5t                              1/1     Running     0             73m
ml-pipeline-794c8cd8b7-z895t                        1/1     Running     7 (77m ago)   89m
ml-pipeline-persistenceagent-68b6c7fddf-zjqt4       1/1     Running     4 (76m ago)   89m
ml-pipeline-scheduledworkflow-7f8667b76b-sgv96      1/1     Running     0             89m
ml-pipeline-ui-649594d7f4-nb58r                     1/1     Running     0             89m
ml-pipeline-viewer-crd-79d4555d8f-tbgzh             1/1     Running     0             89m
ml-pipeline-visualizationserver-6b9c885665-sqptc    1/1     Running     0             89m
mysql-75d57bbfbf-pdfvh                              1/1     Running     0             89m
workflow-controller-5cb6757498-l2vzd                1/1     Running     0             89m

== mlflow
NAME                                READY   STATUS    RESTARTS   AGE
mlflow-deployment-d9f8c7688-7njm8   1/1     Running   0          74m

== postgres
NAME                                           READY   STATUS    RESTARTS   AGE
postgres-release-postgresql-546c65b4db-nbmzd   1/1     Running   0          89m

== redis
NAME                                       READY   STATUS    RESTARTS   AGE
redis-deployment-master-68886f9c8f-mtjxh   1/1     Running   0          89m
```

**브라우저 C.** `http://127.0.0.1:8080`을 연다. 왼쪽에 Pipelines, Experiments, Runs 메뉴가 보이면 KFP UI가 준비된 것이다. 5장에서 이 화면에 실행 그래프가 나타난다. 처음 열 때 화면이 비어 있으면 `ml-pipeline` Pod가 `Running`인지 다시 확인한다.

**완료 확인**

- [ ] `bookenv.py check`가 `All required tools are available.`로 끝난다.
- [ ] `status`의 kubeflow, mlflow, postgres, redis Pod가 모두 `Running`이다.
- [ ] 터미널 B의 포트포워딩이 켜져 있고 `http://127.0.0.1:8080`이 열린다.
- [ ] 책 4~5장 원본 노트북 실습은 [4~5장 환경 설명](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/#book-lab-sop)을 따른다. 이 가이드는 같은 클러스터에서 독립 구현 파이프라인을 실행한다.

## 4장. 실험, 평가와 등록을 연결한다 {#chapter-04}

다시 `ml-platform-engineering-labs` 폴더의 기본 환경으로 돌아온다. 이 경로는 책의 소득 분류를 복제하는 것이 아니라 작은 추천 데이터로 같은 기록과 등록 책임을 익히는 독립 구현이다. 소득 분류 원본은 [4~5장 실행 참조](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/#book-lab-sop)에 별도로 남겼다.

### 4-1. 평점 데이터를 준비한다

**터미널 A, `ml-platform-engineering-labs`, 기본 환경.** 사용자 48명과 영화 32편의 합성 평점을 만들고 사용자별 시간순으로 학습, 검증, 테스트를 나눈다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs movies prepare --output "$W\data\movies"
```

실제 출력:

```text
{
  "result": ".ml-labs\\book-01\\data\\movies"
}
```

### 4-2. 학습하고 MLflow에 기록한다

**터미널 A.** rank 4 SVD 추천 모델을 학습하고 파라미터, 검증 지표와 모델을 같은 run에 남긴다.

```powershell
uv run --locked --extra dev ml-labs movies train --data "$W\data\movies" --output "$W\runs\movies" --work "$W\tracking" --rank 4
```

실제 출력(마이그레이션 로그 생략):

```text
2026/11/07 20:29:01 INFO mlflow.store.db.utils: Creating initial MLflow database tables...
2026/11/07 20:29:03 INFO mlflow.tracking.fluent: Experiment with name 'ml-platform-labs' does not exist. Creating a new experiment.
{
  "result": ".ml-labs\\book-01\\runs\\movies\\candidate.json"
}
```

### 4-3. 평가를 통과한 후보만 등록한다

**터미널 A.** 평가는 검증 RMSE와 인기 기준선 대비 순위 지표를 먼저 보고, 통과한 경우에만 테스트 분할을 연다. 등록은 통과 보고서가 있어야 진행된다.

```powershell
uv run --locked --extra dev ml-labs movies evaluate --candidate "$W\runs\movies\candidate.json" --data "$W\data\movies" --report "$W\reports\movies.json"
$LASTEXITCODE
uv run --locked --extra dev ml-labs register --candidate "$W\runs\movies\candidate.json" --report "$W\reports\movies.json" --name book-movie
(Get-Content "$W\runs\movies\candidate.json" -Raw | ConvertFrom-Json).registered_uri
```

실제 출력(평가 결과는 판정 부분만 남김):

```text
{
  "result": {
    "task": "movies",
    "passed": true,
    "max_validation_rmse": 1.5,
    ...
    "observed_validation_rmse": 0.6722079292983877,
    "ranking_gate": {
      "min_ndcg_lift": null,
      "observed_lift": 0.32112089644232705,
      "passed": true
    },
    "test_policy": "Test split was scored only after the validation gate."
  }
}
0
Successfully registered model 'book-movie'.
Created version '1' of model 'book-movie'.
models:/book-movie/1
```

`$LASTEXITCODE`가 0이 아니면 등록으로 넘어가지 않는다.

### 4-4. MLflow 화면에서 run과 등록 모델을 확인한다

**터미널 B, 기본 환경.** 로컬 Tracking DB를 읽는 MLflow UI를 5001번에 띄운다. 5000번은 3장의 클러스터 MLflow다.

```powershell
Set-Location $HOME\ml-labs-book\ml-platform-engineering-labs
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
$db = (Resolve-Path "$W\tracking\tracking.db").Path.Replace('\', '/')
uv run --locked --extra dev mlflow ui --backend-store-uri "sqlite:///$db" --host 127.0.0.1 --port 5001
```

**브라우저 C.** `http://127.0.0.1:5001`에서 Experiments의 `ml-platform-labs`를 연다. run 하나가 있고 Models 열에 `book-movie v1`이 붙어 있다.

![MLflow ml-platform-labs 실험의 run 목록. run 하나에 book-movie v1 모델이 연결돼 있다.](/images/ml-platform-engineering/guide/guide-ch04-mlflow-runs.png)

run 이름을 누르고 Overview 아래로 내리면 파라미터 `rank=4`, `seed=42`와 검증 지표가 보인다. `test_recall_at_5`는 평가가 통과한 뒤에만 기록된다.

![run 상세 화면의 Parameters와 Metrics. rank 4, seed 42와 validation_rmse 0.672, test_recall_at_5 0.8이 보인다.](/images/ml-platform-engineering/guide/guide-ch04-mlflow-run-metrics.png)

상단 Models 메뉴에서 등록 모델과 별칭을 확인한다. 처음 열 때 새 Model Registry UI 안내 창이 뜨면 닫는다.

![Registered Models 목록에 book-movie Version 1과 champion 별칭이 보인다.](/images/ml-platform-engineering/guide/guide-ch04-mlflow-registry.png)

`Version 1`을 누르면 원천 run과 입력, 출력 스키마가 보인다. 서빙 API가 지켜야 할 계약이 이 스키마다.

![book-movie Version 1 화면. Source Run, champion 별칭, 입력 user_id와 strategy, 출력 user_id, status, recommendations 스키마가 보인다.](/images/ml-platform-engineering/guide/guide-ch04-mlflow-model-version.png)

SQLite는 메타데이터이고 모델 파일은 별도 아티팩트 폴더(`$W\tracking`)에 있다. DB만 복사하면 모델이 함께 복사되지 않는다. UI는 9장까지 켜 두고 확인할 때마다 새로고침해도 된다.

### 4-5. 평가를 일부러 실패시킨다

**터미널 A, 기본 환경.** 기준을 비현실적으로 낮춰 거절 경로를 확인한다. 거절 보고서는 별도 파일에 쓰고 정상 보고서를 덮어쓰지 않는다.

```powershell
uv run --locked --extra dev ml-labs movies evaluate --candidate "$W\runs\movies\candidate.json" --data "$W\data\movies" --report "$W\reports\movies-rejected.json" --max-rmse 0.01
$LASTEXITCODE
uv run --locked --extra dev ml-labs register --candidate "$W\runs\movies\candidate.json" --report "$W\reports\movies-rejected.json" --name must-not-register
$LASTEXITCODE
```

실제 출력:

```text
ml-labs: error: Model validation gate rejected candidate; report: .ml-labs\book-01\reports\movies-rejected.json
2
ml-labs: error: Registry promotion requires a passing movies evaluation report.
2
```

평가와 등록 모두 종료 코드 2로 실패하는 것이 기대 동작이다. 이 거절 평가는 같은 run의 `validation_passed` 태그를 `false`로 바꾸고 `evaluation/validation.json`도 거절 보고서로 갱신한다. 이미 만든 `book-movie` 버전 1은 바뀌지 않는다. run 태그는 마지막 평가만 보여 주므로 출시 판단은 보고서 파일과 등록 버전으로 한다.

### 4-6. Feast로 정의를 등록하고 과거 시점을 조회한다

**터미널 A, tools 환경.** 같은 평점에서 사용자 피처(평균 평점, 평점 수)를 만들고 실제 Feast 저장소에 정의를 등록한다. Feast는 UI 없이 CLI 출력으로 확인한다.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-tools"
uv run --locked --extra feast ml-labs tools feast init --data "$W\data\movies" --output "$W\feast"
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action apply
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action historical --user-id u007
```

실제 출력(경고 줄을 줄임):

```text
Uninstalled 1 package in 17ms
Installed 1 package in 48ms
{
  "repo": ".ml-labs\\book-01\\feast"
}
WARNING:root:Cannot use sqlite_vec for vector search
{
  "action": "apply",
  "dataset_sha256": "9acf3ae528740f8e99f986e3eba5e69377ab04fcdeef77f351338415e8aa5f1b",
  "status": "applied"
}
{
  "action": "historical",
  "user_id": "u007",
  "rows": [
    { "event_timestamp": "2024-12-31T00:00:00+00:00", "average_rating": null, "ratings_count": null,
      "returned_by_feast": false, "point_in_time_correct": true },
    { "event_timestamp": "2025-01-01T00:00:00+00:00", "average_rating": 2.240000009536743, "ratings_count": 1,
      "returned_by_feast": true, "point_in_time_correct": true },
    { "event_timestamp": "2025-01-08T12:00:00+00:00", "average_rating": 2.40625, "ratings_count": 8,
      "returned_by_feast": true, "point_in_time_correct": true },
    { "event_timestamp": "2025-02-13T00:00:00+00:00", "average_rating": 2.780428647994995, "ratings_count": 14,
      "returned_by_feast": true, "point_in_time_correct": true }
  ]
}
```

첫 줄의 `Uninstalled 1 package`, `Installed 1 package`는 uv가 이 extra 조합에 맞춰 패키지 하나를 바꿔 끼운 기록이며 오류가 아니다. 과거 조회는 각 시점까지 관찰된 값만 돌려준다. 첫 평점 이전 시점에는 값이 없고, 이후 시점에는 그때까지의 평균과 개수만 나온다. `point_in_time_correct`는 Feast 결과를 직접 계산한 기대값과 비교한 결과다.

### 4-7. 온라인 조회는 적재 전에 실패하고 적재 후에 성공한다

**터미널 A, tools 환경.** 정의 등록과 값 적재는 다른 작업이다. 온라인 저장소는 materialize가 채운다.

```powershell
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action online --user-id u007
$LASTEXITCODE
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action materialize
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action online --user-id u007
```

실제 출력(경고 줄을 줄임):

```text
ml-labs: error: No online features for 'u007'. Run `ml-labs tools feast run --action apply` and `--action materialize` first (the online store is filled only by materialization).
2
Materializing 1 feature views from 2025-01-01 08:59:59+09:00 to 2025-01-14 09:00:01+09:00 into the sqlite online store.

user_movie_stats:
100%|█████████████████████████████████████████████████████████████| 48/48 [00:00<00:00, 1981.87it/s]
{
  "action": "materialize",
  "status": "materialized",
  "start": "2024-12-31T23:59:59+00:00",
  "end": "2025-01-14T00:00:01+00:00"
}
{
  "action": "online",
  "user_id": "u007",
  "features": {
    "user_id": ["u007"],
    "average_rating": [2.780428647994995],
    "observed_at_unix": [1736812800],
    "ratings_count": [14]
  }
}
```

이제 학습 평점에서 계산한 최신 피처를 읽는다. 이 예제의 Online store는 Feast의 SQLite 구현이다. 책의 Redis 온라인 저장소를 대신 검증한 것은 아니다.

**완료 확인**

- [ ] `registered_uri`가 `models:/book-movie/1`이다.
- [ ] MLflow 화면에서 run, 지표와 등록 버전이 보인다.
- [ ] 거절 평가와 `must-not-register` 등록이 모두 종료 코드 2로 실패했다.
- [ ] 온라인 조회가 materialize 전에는 실패하고 뒤에는 `ratings_count` 14를 돌려준다.

## 5장. 컴포넌트를 연결하고 클러스터에서 실행한다 {#chapter-05}

KFP SDK로 데이터 준비, 학습과 평가를 컴포넌트로 묶는다. 먼저 로컬에서 컴파일과 컴포넌트 본문을 확인하고, 그다음 실습 이미지를 만들어 3장의 클러스터에서 실제 Pod로 실행한다.

### 5-1. 파이프라인을 컴파일하고 YAML을 읽는다

**터미널 A, `ml-platform-engineering-labs`, tools 환경.** 이미지를 지정하지 않으면 자리표시자 이미지로 컴파일된다. 구조를 읽는 용도이며 그대로 제출하지 않는다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-tools"
$revision = git rev-parse HEAD
uv run --locked --extra pipeline ml-labs tools kfp compile --source-revision $revision --output "$W\kfp\movie-pipeline.yaml"
Get-Content "$W\kfp\movie-pipeline.yaml" -TotalCount 12
```

실제 출력:

```text
{
  "output": ".ml-labs\\book-01\\kfp\\movie-pipeline.yaml",
  "image": "SET-YOUR-REGISTRY/ml-platform-engineering-labs:SET-IMAGE-TAG",
  "source_revision": "ff23b38f88d88268216e2985ff5b6ed0c3defb8c",
  "image_is_placeholder": true,
  "submitted": false,
  "warning": "Image is a placeholder; build/push the repo Dockerfile and recompile with --image <registry>/<name>@sha256:<digest> before submitting."
}
# PIPELINE DEFINITION
# Name: ml-labs-movie-recommender
# Description: Synthetic movie data -> SVD recommender (MLflow) -> gated holdout evaluation
# Inputs:
#    items: int [Default: 32.0]
#    max_rmse: float [Default: 1.5]
#    mlflow_root: str [Default: '/workspace/mlflow']
#    rank: int [Default: 4.0]
#    seed: int [Default: 42.0]
#    source_revision: str [Default: 'ff23b38f88d88268216e2985ff5b6ed0c3defb8c']
#    users: int [Default: 48.0]
components:
```

YAML 아래쪽 `root.dag.tasks`에서 작업 사이의 연결을 볼 수 있다. 평가 작업은 준비 작업의 `dataset`과 학습 작업의 `model`을 입력 아티팩트로 받는다.

```text
      evaluate-movie-recommender:
        dependentTasks:
        - prepare-movie-data
        - train-movie-recommender
        inputs:
          artifacts:
            dataset:
              taskOutputArtifact:
                outputArtifactKey: dataset
                producerTask: prepare-movie-data
            model:
              taskOutputArtifact:
                outputArtifactKey: model
                producerTask: train-movie-recommender
        taskInfo:
          name: evaluate-holdout
```

### 5-2. 컴포넌트 본문을 로컬에서 실행한다

**터미널 A, tools 환경.** 같은 컴포넌트 함수를 로컬 프로세스에서 호출해 데이터, MLflow 모델 묶음과 평가 파일이 이어지는지 본다. Kubernetes Pod를 실행하는 검사는 아니다.

```powershell
uv run --locked --extra dev --extra pipeline pytest -q -p no:warnings tests\test_optional_integrations.py -k "native_kfp or kfp_component_bodies"
```

실제 출력:

```text
Uninstalled 1 package in 15ms
Installed 1 package in 34ms
..                                                                       [100%]
2 passed, 8 deselected in 6.31s
```

### 5-3. 실습 이미지를 만든다

**터미널 A, `ml-platform-engineering-labs`.** 저장소의 `Dockerfile`은 `uv.lock`의 core와 `pipeline` 의존성, `ml_labs` 패키지를 Python 3.12.12 이미지에 설치한다. 커밋을 빌드 인자로 넘겨 이미지 라벨과 실행 환경 변수에 남긴다.

```powershell
$revision = git rev-parse HEAD
docker build --platform linux/amd64 --build-arg SOURCE_REVISION=$revision -t book-labs:ff23b38 .
docker images book-labs
```

실제 출력(빌드 로그 마지막 부분):

```text
#14 [stage-0 8/9] RUN uv pip install --system --no-cache --no-deps .     && python -c "import kfp, ml_labs.movies, ml_labs.data; print('ml_labs image ready')"
#14 1.693 ml_labs image ready
#14 DONE 10.1s
#16 naming to docker.io/library/book-labs:ff23b38 0.0s done
#16 unpacking to docker.io/library/book-labs:ff23b38 5.7s done
#16 DONE 26.8s
IMAGE               ID             DISK USAGE   CONTENT SIZE   EXTRA
book-labs:ff23b38   03760880abcd       1.14GB          254MB
```

의존성 설치 단계가 약 2분 걸렸다. `python:3.12.12-slim-bookworm`이나 `ghcr.io/astral-sh/uv:0.12.3`을 받다가 TLS 시간 초과가 나면 같은 명령을 다시 실행한다.

### 5-4. 이미지를 kind 노드에 넣는다

**터미널 A.** kind 노드는 로컬 Docker 이미지를 직접 보지 못한다. 레지스트리에 push하지 않고 노드의 containerd에 복사한다.

```powershell
kind load docker-image book-labs:ff23b38 --name book-env
docker exec book-env-control-plane crictl images | Select-String "book-labs|IMAGE"
```

실제 출력:

```text
Image: "book-labs:ff23b38" with ID "sha256:03760880abcd5266131afd12415e007bf1274fa0d0914f925060d539fdedc062" not yet present on node "book-env-control-plane", loading...
IMAGE                                                TAG                          IMAGE ID            SIZE
docker.io/library/book-labs                          ff23b38                      20096132a8c97       254MB
```

`content digest ... not found` 오류가 나오면 Docker Desktop의 containerd 이미지 저장소와 kind의 가져오기 방식이 맞지 않는 경우다. 이때는 압축 파일을 거쳐 넣는다.

```powershell
docker save book-labs:ff23b38 -o "$W\book-labs.tar"
kind load image-archive "$W\book-labs.tar" --name book-env
```

태그가 `latest`가 아니므로 Pod의 `imagePullPolicy`는 `IfNotPresent`가 되고 노드에 넣은 이미지를 그대로 쓴다.

### 5-5. 실제 이미지로 다시 컴파일하고 KFP 2.4.1에 맞춘다

**터미널 A, tools 환경.** 같은 파이프라인을 실습 이미지로 컴파일한다.

```powershell
uv run --locked --extra pipeline ml-labs tools kfp compile --source-revision $revision --image book-labs:ff23b38 --output "$W\kfp\movie-pipeline-cluster.yaml"
Select-String -Path "$W\kfp\movie-pipeline-cluster.yaml" -Pattern "image:"
```

실제 출력:

```text
{
  "output": ".ml-labs\\book-01\\kfp\\movie-pipeline-cluster.yaml",
  "image": "book-labs:ff23b38",
  "source_revision": "ff23b38f88d88268216e2985ff5b6ed0c3defb8c",
  "image_is_placeholder": false,
  "submitted": false
}
.ml-labs\book-01\kfp\movie-pipeline-cluster.yaml:133:        image: book-labs:ff23b38
.ml-labs\book-01\kfp\movie-pipeline-cluster.yaml:163:        image: book-labs:ff23b38
.ml-labs\book-01\kfp\movie-pipeline-cluster.yaml:204:        image: book-labs:ff23b38
```

이 YAML을 그대로 3장의 KFP 2.4.1 백엔드에 제출하면 준비와 학습은 성공하지만 평가 작업의 driver가 시작하지 못하고 run이 `FAILED`가 된다. 실습 코드는 학습과 평가 작업에 표시 이름(`train-svd-recommender`, `evaluate-holdout`)을 붙이는데, KFP 2.4.1의 driver는 상위 작업의 아티팩트를 표시 이름으로 찾다가 YAML의 작업 키(`train-movie-recommender`)와 맞지 않아 멈춘다. 이번 실행에서 관찰한 driver 로그는 다음과 같다.

```text
panic: runtime error: invalid memory address or nil pointer dereference
github.com/kubeflow/pipelines/backend/src/v2/driver.resolveUpstreamArtifacts(...)
	/go/src/github.com/kubeflow/pipelines/backend/src/v2/driver/driver.go:1519 +0x4b9
```

![표시 이름을 그대로 둔 첫 제출의 KFP 그래프. prepare-movie-data와 train-svd-recommender는 성공했고 evaluate-holdout은 시작하지 못한 채 run이 실패했다.](/images/ml-platform-engineering/guide/guide-ch05-kfp-run-failed.png)

소스는 고치지 않고 제출용 YAML에서만 표시 이름을 작업 키와 같게 바꾼다.

```powershell
uv run --locked --extra pipeline python -c "import sys,yaml; d=yaml.safe_load(open(sys.argv[1],encoding='utf-8')); [t['taskInfo'].update(name=k) for k,t in d['root']['dag']['tasks'].items()]; yaml.safe_dump(d,open(sys.argv[2],'w',encoding='utf-8'),sort_keys=False); print({k:t['taskInfo']['name'] for k,t in d['root']['dag']['tasks'].items()})" "$W\kfp\movie-pipeline-cluster.yaml" "$W\kfp\movie-pipeline-kfp24.yaml"
```

실제 출력:

```text
{'evaluate-movie-recommender': 'evaluate-movie-recommender', 'prepare-movie-data': 'prepare-movie-data', 'train-movie-recommender': 'train-movie-recommender'}
```

### 5-6. KFP에 제출하고 완료까지 기다린다

**터미널 A, tools 환경, 3장의 포트포워딩이 켜진 상태.** 로컬 KFP standalone은 인증이 없으므로 `http://127.0.0.1:8080`에 바로 제출한다. 인증이 있는 다른 클러스터에는 이 주소와 방식을 그대로 쓰지 않는다.

```powershell
uv run --locked --extra pipeline python -c "import sys,kfp; c=kfp.Client(host='http://127.0.0.1:8080'); run=c.create_run_from_pipeline_package(sys.argv[1],arguments={'rank':4},experiment_name='guide-book-labs',run_name='guide-movie-rank4',enable_caching=False); r=c.wait_for_run_completion(run.run_id,timeout=900); print(run.run_id, r.state); [print(t.display_name, t.state) for t in r.run_details.task_details if t.display_name in ('prepare-movie-data','train-movie-recommender','evaluate-movie-recommender')]" "$W\kfp\movie-pipeline-kfp24.yaml"
```

실제 출력(`FutureWarning` 줄 생략):

```text
Experiment details: http://127.0.0.1:8080/#/experiments/details/652161b2-4c8f-47b7-a416-cb78409f5f44
Run details: http://127.0.0.1:8080/#/runs/details/917f69c6-a703-4720-a3f6-b8dd6a04c2a9
917f69c6-a703-4720-a3f6-b8dd6a04c2a9 SUCCEEDED
prepare-movie-data SUCCEEDED
train-movie-recommender SUCCEEDED
evaluate-movie-recommender SUCCEEDED
```

명령 시작부터 완료까지 약 1분 50초가 걸렸다. 각 컴포넌트는 Pod 안의 `/workspace/mlflow`에 임시 SQLite MLflow를 만들고, 그 폴더 전체를 KFP 아티팩트(클러스터 MinIO)로 다음 작업에 넘긴다. 3장의 클러스터 MLflow(5000번)에는 기록하지 않는다. 클러스터 MLflow에 남기려면 컴포넌트가 그 서비스 주소와 S3 자격 증명을 받도록 따로 구성해야 하며, 이 판에서는 구현하지 않았다.

### 5-7. KFP 화면에서 그래프, 지표와 로그를 확인한다

**브라우저 C.** 출력의 `Run details` 주소를 연다. 세 작업과 그 사이의 아티팩트가 그래프로 보이고 모두 초록색 체크가 붙는다.

![성공한 KFP run 그래프. prepare-movie-data, train-movie-recommender, evaluate-movie-recommender가 모두 성공했고 dataset, model, evaluated_model, metrics, report 아티팩트가 연결돼 있다.](/images/ml-platform-engineering/guide/guide-ch05-kfp-run-graph.png)

`metrics` 아티팩트를 누르고 Visualization 탭을 열면 평가 컴포넌트가 남긴 스칼라 지표가 보인다. 4장의 로컬 실행과 같은 seed와 rank이므로 `validation_rmse` 0.672208, `test_recall_at_5` 0.8로 값이 같다.

![metrics 아티팩트의 Scalar Metrics. baseline_rmse 0.830816, test_recall_at_5 0.8, test_relevant_rows 10, validation_rmse 0.672208이 보인다.](/images/ml-platform-engineering/guide/guide-ch05-kfp-metrics.png)

평가 작업을 누르고 Input/Output 탭을 보면 입력 파라미터와 상위 작업의 아티팩트 위치가 보인다. 폴더 형태 아티팩트는 미리보기가 `Error in retrieving artifact preview`로 나오는데, 파일 하나가 아닌 디렉터리여서 생기는 표시이며 실행 실패가 아니다.

![평가 작업의 Input/Output 탭. max_rmse 1.5, mlflow_root, source_revision과 dataset, model 아티팩트의 minio 경로가 보인다.](/images/ml-platform-engineering/guide/guide-ch05-kfp-eval-io.png)

Logs 탭의 마지막 줄들은 평가 결과와 MLflow 묶음을 MinIO에 올린 뒤 `publish success`로 끝난다.

![평가 작업의 Logs 탭. evaluated_model 파일을 uploadFile로 올린 뒤 publish success와 sub-process exited가 출력됐다.](/images/ml-platform-engineering/guide/guide-ch05-kfp-eval-logs.png)

같은 내용을 터미널에서도 볼 수 있다.

```powershell
kubectl --context kind-book-env -n kubeflow get pods | Select-String "ml-labs-movie-recommender"
```

**완료 확인**

- [ ] 로컬 컴포넌트 검사 2개가 통과했다.
- [ ] `crictl images`에 `book-labs:ff23b38`이 보인다.
- [ ] KFP run이 `SUCCEEDED`이고 세 작업이 모두 성공했다.
- [ ] 실패했다면 이미지 빌드 실패, `ErrImagePull`(노드에 이미지 없음), driver 실패(5-5의 표시 이름), 저장소 연결 오류를 나눠서 본다. 컴파일 성공만으로 클러스터 실행을 완료로 표시하지 않는다.

## 6장. 등록 모델을 HTTP와 BentoML로 사용한다 {#chapter-06}

4장에서 등록한 `book-movie` 버전 1을 두 방식으로 서빙한다. FastAPI 서버는 후보 명세를 읽어 등록 버전을 고정하고, BentoML은 같은 MLflow 모델을 자기 모델 저장소로 가져와 서비스로 묶는다.

### 6-1. 추천 API 서버를 켠다

**터미널 B, `ml-platform-engineering-labs`, 기본 환경.** 서버는 켜 둔다.

```powershell
Set-Location $HOME\ml-labs-book\ml-platform-engineering-labs
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
Remove-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue
uv run --locked --extra dev ml-labs serve --movies "$W\runs\movies\candidate.json" --host 127.0.0.1 --port 8000
```

`Uvicorn running on http://127.0.0.1:8000`이 나오면 준비된 것이다.

### 6-2. 기존 사용자와 처음 보는 사용자를 비교한다

**터미널 A.** `ConvertTo-Json`을 붙이면 중첩된 추천 목록까지 그대로 보인다.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 6
$body = @{ user_id = "u000" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/recommend -Method Post -ContentType application/json -Body $body | ConvertTo-Json -Depth 6
$body = @{ user_id = "new-user" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/recommend -Method Post -ContentType application/json -Body $body | ConvertTo-Json -Depth 6
```

실제 출력(추천 목록은 처음 두 개만 남김):

```text
{
  "status": "ok",
  "models": { "cards": false, "movies": true, "rag": false },
  "movie_release_id": null,
  "feast_enabled": false,
  "rag_release_configured": false
}
{
  "user_id": "u000",
  "status": "personalized",
  "recommendations": [
    { "item_id": "m025", "score": 3.972719144406785 },
    { "item_id": "m022", "score": 3.758731167815679 },
    ...
  ],
  "feature_routing": null,
  "model_uri": "models:/book-movie/1",
  "release_id": null
}
{
  "user_id": "new-user",
  "status": "cold_start_popularity",
  "recommendations": [
    { "item_id": "m031", "score": 3.3113125 },
    { "item_id": "m025", "score": 3.2506818181818176 },
    ...
  ],
  "feature_routing": null,
  "model_uri": "models:/book-movie/1",
  "release_id": null
}
```

학습에 있던 사용자는 `personalized`, 처음 보는 사용자는 인기 기준선인 `cold_start_popularity`로 응답한다. 두 응답 모두 `model_uri`에 구체 버전이 들어 있다.

### 6-3. Swagger 화면에서 같은 요청을 보낸다

**브라우저 C.** `http://127.0.0.1:8000/docs`를 열고 `POST /recommend`를 펼친 뒤 `Try it out`을 누른다. 요청 본문에 `{"user_id": "u000"}`을 넣고 `Execute`를 누른다.

![FastAPI Swagger의 POST /recommend 요청과 응답. user_id u000에 대해 status personalized, 추천 5개와 model_uri models:/book-movie/1이 반환됐다.](/images/ml-platform-engineering/guide/guide-ch06-api-recommend.png)

같은 화면에서 `{"user_id": "new-user"}`로 바꿔 다시 실행한다.

![같은 엔드포인트에 new-user를 보낸 응답. status가 cold_start_popularity이고 인기 순 추천 5개가 반환됐다.](/images/ml-platform-engineering/guide/guide-ch06-api-cold-start.png)

확인이 끝나면 터미널 B에서 `Ctrl+C`로 서버를 종료한다. 10장에서 같은 포트를 다시 쓴다.

### 6-4. BentoML로 모델을 가져오고 Bento를 만든다

**터미널 A, bento 환경.** BentoML 모델 저장소를 이 실습 폴더 안으로 지정한다. 기본 위치(`%USERPROFILE%\bentoml`)는 다른 프로젝트와 공유되며, 다른 BentoML 서버가 켜져 있으면 `task_result.db`가 잠겨 6-5의 서버 시작이 실패한다.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-bento"
$env:BENTOML_HOME = Join-Path (Resolve-Path $W).Path "bentoml-home"
uv run --locked --extra bento ml-labs tools bento build --candidate "$W\runs\movies\candidate.json" --output "$W\bento"
uv run --locked --extra bento bentoml build "$W\bento"
uv run --locked --extra bento bentoml models list
uv run --locked --extra bento bentoml list
```

실제 출력(`pkg_resources` 경고 생략):

```text
{
  "output": ".ml-labs\\book-01\\bento\\bentofile.yaml"
}
INFO: Locking PyPI package versions.
INFO: Locking packages for x86_64-unknown-linux-gnu. Pass `--platform` option to specify the platform.

Successfully built Bento(tag="ml-labs-movies:nql2o762ug3h3laz").
 Tag                           Module          Size        Creation Time
 ml-labs-movies:njdahiw2ugjh…  bentoml.mlflow  219.72 KiB  2026-11-07 20:50:23
 Tag                              Size       Model Size  Creation Time
 ml-labs-movies:nql2o762ug3h3laz  19.24 KiB  219.72 KiB  2026-11-07 20:50:26
```

`tools bento build`는 MLflow 모델을 BentoML 저장소로 가져오고 `service.py`와 `bentofile.yaml`을 만든다. `bentoml build`는 그 둘을 Bento 패키지로 묶는다. 패키지 잠금 단계는 PyPI에 접속한다. 컨테이너 생성(`bentoml containerize`)과 Kubernetes 배포는 여기에 포함되지 않는다. 이 경로는 BentoML 1.3.10의 구현이며 책의 1.1.10 Service, Runner 선언을 섞지 않는다.

### 6-5. Bento 서비스를 켠다

**터미널 B, bento 환경.** 6-1의 서버를 끈 같은 창을 써도 된다.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-bento"
$env:BENTOML_HOME = Join-Path (Resolve-Path $W).Path "bentoml-home"
uv run --locked --extra bento bentoml serve service:PlatformLabService --working-dir "$W\bento" --host 127.0.0.1 --port 3000
```

`Converting 'PlatformLabService' to lowercase` 경고는 정상이다. 3000번을 이미 다른 프로그램이 쓰고 있으면 엉뚱한 서비스가 응답하므로 먼저 `Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue`로 비어 있는지 확인한다. 이번 실행에서는 다른 실습 서비스가 3000번을 쓰고 있어 `--port 3010`으로 실행했고, 아래 요청과 화면도 3010번에서 얻었다.

### 6-6. Bento에 요청한다

**터미널 A.** 요청 구조가 FastAPI와 다르다. BentoML은 메서드 인자 이름(`request`)으로 본문을 한 번 더 감싼다.

```powershell
$body = @{ request = @{ user_id = "u000" } } | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:3000/predict -Method Post -ContentType application/json -Body $body | ConvertTo-Json -Depth 6
```

실제 출력(추천 목록 일부):

```text
{
  "user_id": "u000",
  "status": "personalized",
  "recommendations": [
    { "item_id": "m025", "score": 3.972719144406785 },
    { "item_id": "m022", "score": 3.758731167815679 },
    ...
  ]
}
```

같은 등록 모델이므로 6-2의 FastAPI와 추천과 점수가 같다. **브라우저 C**에서 `http://127.0.0.1:3000/`을 열면 BentoML의 Swagger 화면이 나온다. `POST /predict`의 `Try it out`에 `{"request": {"user_id": "u000"}}`을 넣고 실행한다.

![BentoML Swagger의 POST /predict 요청과 응답. request로 감싼 user_id u000 요청에 personalized 추천 5개가 반환됐고 응답 헤더 server가 BentoML Service/ml-labs-movies다.](/images/ml-platform-engineering/guide/guide-ch06-bento-predict.png)

확인이 끝나면 터미널 B에서 `Ctrl+C`로 종료하고 `Remove-Item Env:BENTOML_HOME`으로 환경 변수를 지운다.

**완료 확인**

- [ ] FastAPI 응답의 `model_uri`가 `models:/book-movie/1`이다.
- [ ] 기존 사용자는 `personalized`, 새 사용자는 `cold_start_popularity`다.
- [ ] `bentoml list`에 Bento가 하나 있고 `/predict`가 같은 추천을 돌려준다.
- [ ] 모델 등록, Bento 생성, 서버 시작, 요청 성공을 각각 확인했다. 드리프트 보고서는 11장에서 같은 데이터에 연결한다.

## 7장. 다음 학습이 사용할 데이터를 준비한다 {#chapter-07}

기본 환경으로 돌아온다. 앞에서 만든 추천 데이터는 다시 덮어쓰지 않는다. 여기서는 탐지 학습용 이미지 데이터와 실제 MovieLens로 바꾸는 경로를 준비한다.

### 7-1. 합성 카드 이미지와 YOLO 라벨을 만든다

**터미널 A, 기본 환경.** 학습 80장, 검증 20장, 테스트 20장을 만든다. 실제 신분증이나 개인정보는 들어 있지 않다.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs cards prepare --output "$W\data\cards" --train 80 --validation 20 --test 20
Get-Content "$W\data\cards\manifest.json"
```

실제 출력:

```text
{
  "result": "C:\\Users\\<사용자>\\...\\.ml-labs\\book-01\\data\\cards"
}
{
  "dataset": "synthetic-cards",
  "seed": 42,
  "sha256": "3b33e08ea983fa42431bbfc7dc1b07e203afa21fec1c678437c30ac7ed1c19aa",
  "counts": {
    "train": 80,
    "validation": 20,
    "test": 20
  },
  "limitations": "Axis-aligned generated cards, independent images, no identity data; not OCR."
}
```

### 7-2. 이미지와 라벨의 짝을 확인한다

**터미널 A.** 이미지와 같은 이름(stem)의 `.txt`가 라벨이다. YOLO 라벨 한 줄은 클래스, 정규화한 중심 x, 중심 y, 너비, 높이다.

```powershell
Get-ChildItem "$W\data\cards\images\train" | Select-Object -First 3 Name, Length
Get-ChildItem "$W\data\cards\labels\train" | Select-Object -First 3 Name, Length
Get-Content "$W\data\cards\labels\train\train-0001.txt"
```

실제 출력:

```text
Name                 Length
----                 ------
train-0000.png        43666
train-0001.png        37664
train-0002.png        37428
train-0000.txt            0
train-0001.txt           39
train-0002.txt           39
0 0.355469 0.527344 0.507812 0.273438
```

크기가 0인 라벨은 카드가 없는 음성 표본이다. 음성 표본이 있어야 아무것도 없는 화면에서 상자를 그리지 않는 능력을 평가할 수 있다. `train-0001.png`는 128x128 잡음 배경 위에 카드 모양 사각형이 하나 있다.

![합성 카드 학습 이미지 train-0001.png. 잡음 배경 위에 분홍색 카드 모양 사각형이 있다.](/images/ml-platform-engineering/guide/guide-ch07-card-sample.png)

### 7-3. 실제 MovieLens로 바꾸는 경로를 확인한다

**터미널 A, 기본 환경.** [GroupLens의 이용 조건](https://grouplens.org/datasets/movielens/latest/)을 먼저 읽는다. 원본 압축 파일과 변환 데이터는 저장소에 커밋하지 않는다.

```powershell
New-Item -ItemType Directory -Path "$W\downloads" -Force | Out-Null
Invoke-WebRequest https://files.grouplens.org/datasets/movielens/ml-latest-small.zip -OutFile "$W\downloads\ml-latest-small.zip"
uv run --locked --extra dev ml-labs movies import-movielens --archive "$W\downloads\ml-latest-small.zip" --output "$W\data\movielens"
Get-Content "$W\data\movielens\manifest.json"
```

실제 출력:

```text
{
  "result": ".ml-labs\\book-01\\data\\movielens"
}
{
  "dataset": "movielens-latest-small",
  "rows": 100836,
  "sha256": "040461a97369a50dddec17d460ae4d11be07d5e8a3ebecb665cba20dbdda02a1",
  "archive_sha256": "28cef425f57f870a1b4d8e32d100017b4dd8f3238481430fb9bca8705100d27d",
  "source": "https://grouplens.org/datasets/movielens/latest/",
  "rating_transform": "1 + (original_rating - 0.5) * 4 / 4.5",
  "split": "per-user chronological timestamp groups, 80/10/10 of unique timestamps",
  "license": "MovieLens terms apply; archive and derived data must not be committed."
}
```

압축 파일은 약 1MB이고 평점 100,836건이 변환된다. 가져오기는 원천 지문, 평점 변환식과 사용자별 시간 분할을 기록한다. 책의 25M 전체 자료를 현재 조밀 SVD에 바로 넣는 명령은 아니다. 이후 장은 재현성을 위해 합성 평점을 계속 쓴다.

**완료 확인**

- [ ] `counts`가 80, 20, 20이다.
- [ ] 라벨 파일 중 빈 파일(음성 표본)과 한 줄짜리 파일이 함께 있다.
- [ ] MovieLens `manifest.json`에 `rows`, 변환식과 분할 방식이 기록됐다.
- [ ] `random_state`를 고정한 것만으로 미래 정보나 인접 프레임 누수가 해결되지 않는다는 점을 확인했다.

## 8장. 기준선과 실제 탐지 학습을 구분한다 {#chapter-08}

규칙 기반 색상 기준선과 실제 YOLOv8 학습을 같은 데이터, 같은 평가로 비교한다.

### 8-1. 색상 기준선을 학습하고 등록한다

**터미널 A, 기본 환경.** 학습이라 부르지만 색상 임계값을 정하는 규칙 기준선이다. 비교 대상이 있어야 학습 모델의 가치를 판단할 수 있다.

```powershell
uv run --locked --extra dev ml-labs cards train --data "$W\data\cards" --output "$W\runs\cards" --work "$W\tracking"
uv run --locked --extra dev ml-labs cards evaluate --candidate "$W\runs\cards\candidate.json" --data "$W\data\cards" --report "$W\reports\cards.json"
uv run --locked --extra dev ml-labs register --candidate "$W\runs\cards\candidate.json" --report "$W\reports\cards.json" --name book-card-baseline
```

실제 출력(평가 결과는 판정 부분만):

```text
{
  "result": ".ml-labs\\book-01\\runs\\cards\\candidate.json"
}
{
  "result": {
    "task": "cards",
    "passed": true,
    "min_mean_iou": 0.75,
    "validation_mean_iou": 0.9999976948801512,
    "metrics": {
      "images": 20,
      "mean_iou": 0.9999983959985037,
      "box_recall_iou_0_5": 1.0,
      "negative_images": 4,
      "false_positives": 0
    },
    "candidate": { "backend": "color_component_baseline", ... },
    "split": "test",
    "test_policy": "Test split opened after passing the validation IoU gate."
  }
}
Successfully registered model 'book-card-baseline'.
Created version '1' of model 'book-card-baseline'.
```

합성 카드는 배경과 색이 뚜렷하게 달라 규칙만으로 IoU가 1에 가깝다. 이 숫자는 실제 촬영 환경의 성능이 아니라 데이터가 쉽다는 신호로 읽는다.

### 8-2. vision 환경과 Ultralytics 설정을 격리한다

**터미널 A, vision 환경.** Ultralytics는 사용자 폴더의 설정 파일을 공유하고, 설치돼 있으면 MLflow 자동 콜백을 켠다. Windows에서는 그 콜백이 별도 `runs\mlflow`에 기록하거나 Windows 경로를 URI로 잘못 해석해 학습 전에 실패할 수 있다. 설정을 실습 폴더로 옮기고 자동 콜백과 동기화를 끈다. 실습 코드가 학습 뒤에 같은 Tracking DB에 모델을 직접 기록한다.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-vision"
New-Item -ItemType Directory -Path "$W\yolo-config" -Force | Out-Null
$env:YOLO_CONFIG_DIR = (Resolve-Path "$W\yolo-config").Path
uv run --locked --extra vision yolo settings mlflow=False sync=False
```

실제 출력(일부):

```text
Creating new Ultralytics Settings v0.0.6 file ✅
View Ultralytics Settings with 'yolo settings' or at 'C:\Users\<사용자>\...\.ml-labs\book-01\yolo-config\settings.json'
...
  "sync": false,
  ...
  "mlflow": false,
```

이 설정은 다른 프로젝트의 Ultralytics 설정을 바꾸지 않는다. 새 터미널에서 이어 할 때도 `YOLO_CONFIG_DIR`을 다시 지정한다.

### 8-3. YOLOv8n을 CPU로 10 epoch 학습한다

**터미널 A, vision 환경.** 사전학습 가중치 `yolov8n.pt`에서 시작해 카드 한 클래스로 미세조정한다. 처음 실행하면 가중치(약 6MB)와 글꼴을 내려받는다.

```powershell
uv run --locked --extra vision ml-labs cards train --data "$W\data\cards" --output "$W\runs\cards-yolo" --work "$W\tracking" --backend yolov8 --epochs 10
```

실제 출력(일부):

```text
Ultralytics 8.3.40 🚀 Python-3.12.12 torch-2.5.1+cpu CPU (13th Gen Intel Core(TM) i7-1360P)
engine\trainer: task=detect, mode=train, model=yolov8n.pt, ..., epochs=10, ..., imgsz=128, ..., device=cpu, ...
Overriding model.yaml nc=80 with nc=1
Transferred 319/355 items from pretrained weights
...
                 Class     Images  Instances      Box(P          R      mAP50  mAP50-95)
                   all         20         16      0.987          1      0.995      0.976
Results saved to .ml-labs\book-01\runs\cards-yolo\yolo\synthetic-cards
{
  "result": ".ml-labs\\book-01\\runs\\cards-yolo\\candidate.json"
}
```

이번 실행은 41초가 걸렸다. 마지막 표는 검증 20장(카드 16개)에 대한 Ultralytics의 내부 검증이다.

### 8-4. 학습 곡선과 검증 예측을 읽는다

**터미널 A 또는 탐색기.** 결과 폴더에는 가중치와 학습 그림이 남는다.

```powershell
Get-ChildItem "$W\runs\cards-yolo\yolo\synthetic-cards" -Recurse -Include *.pt, results.png, val_batch0_pred.jpg, results.csv | Select-Object Name, Length
Start-Process "$W\runs\cards-yolo\yolo\synthetic-cards\results.png"
```

실제 출력:

```text
Name                 Length
----                 ------
best.pt             6190883
last.pt             6190883
results.csv            1332
results.png          282859
val_batch0_pred.jpg  107486
```

`results.png`에서 손실은 내려가고 mAP50은 3 epoch부터 0.98 이상이다. precision은 4 epoch까지 0.01대에 머물다 5 epoch에 0.97로 뛰었다. 초기에는 낮은 신뢰도의 상자를 많이 그리다가 학습이 진행되며 정리된 것이다.

![YOLO 학습 결과 그래프 results.png. train과 val의 box, cls, dfl 손실이 줄고 precision은 5 epoch에 0.97로 오르며 mAP50은 0.995, mAP50-95는 0.976에 도달했다.](/images/ml-platform-engineering/guide/guide-ch08-yolo-results.png)

`val_batch0_pred.jpg`는 검증 이미지 16장에 대한 예측이다. 카드가 있는 이미지에는 `synthetic_id_card`와 신뢰도가 표시되고 빈 배경에는 상자가 없다. 신뢰도가 0.3~0.9로 퍼져 있어 10 epoch 모델이 아직 확신이 낮다는 것도 보인다.

![검증 배치 예측 val_batch0_pred. 4x4 격자의 합성 카드 이미지 중 카드가 있는 칸에 신뢰도 0.3에서 0.9 사이의 상자가 그려졌고 빈 배경 칸에는 상자가 없다.](/images/ml-platform-engineering/guide/guide-ch08-yolo-val-pred.png)

### 8-5. 실습 평가로 판정하고 등록한다

**터미널 A, vision 환경.** Ultralytics의 mAP와 별개로 기준선과 같은 IoU 평가를 적용한다. 검증 IoU 게이트를 통과해야 테스트를 연다.

```powershell
uv run --locked --extra vision ml-labs cards evaluate --candidate "$W\runs\cards-yolo\candidate.json" --data "$W\data\cards" --report "$W\reports\cards-yolo.json" --min-iou 0.5
uv run --locked --extra vision ml-labs register --candidate "$W\runs\cards-yolo\candidate.json" --report "$W\reports\cards-yolo.json" --name book-card-yolo
```

실제 출력(판정 부분):

```text
{
  "result": {
    "task": "cards",
    "passed": true,
    "min_mean_iou": 0.5,
    "validation_mean_iou": 0.8492493319417679,
    "metrics": {
      "images": 20,
      "mean_iou": 0.9675049159141798,
      "box_recall_iou_0_5": 1.0,
      "negative_images": 4,
      "false_positives": 0
    },
    "candidate": {
      "backend": "yolov8",
      "validation": { "detection_rate": 0.7, "mean_iou": 0.8492493319417679, "box_recall_iou_0_5": 0.875, ... },
      ...
    }
  }
}
Successfully registered model 'book-card-yolo'.
Created version '1' of model 'book-card-yolo'.
```

검증에서 카드 16개 중 2개를 놓쳐(`box_recall_iou_0_5` 0.875) 기준선보다 낮다. 그래도 설정한 IoU 0.5 게이트는 통과했다. 기준선보다 낮은 학습 모델을 왜 등록하는지는 정책 문제다. 이 실습은 학습 가중치를 저장하고 다시 읽어 서빙하는 경로를 익히는 것이 목적이며, 실제 운영에서는 기준선을 넘지 못한 후보를 출시하지 않는 규칙을 둘 수 있다.

### 8-6. MLflow에서 YOLO 후보를 확인한다

**브라우저 C.** 4장의 MLflow UI(5001번)를 새로고침하고 Models 열이 `book-card-yolo v1`인 run을 연다. 파라미터는 `backend=yolov8`, `epochs=10`이고 검증과 테스트 지표가 함께 남는다.

![YOLO 후보 run의 Parameters와 Metrics. backend yolov8, epochs 10과 validation_detection_rate 0.7, validation_mean_iou 0.849, test_mean_iou 0.968, test_box_recall_iou_0_5 1이 보인다.](/images/ml-platform-engineering/guide/guide-ch08-mlflow-yolo-run.png)

### 8-7. 작은 실제 학습과 재로딩을 테스트로 점검한다

**터미널 A, vision 환경.** 이 테스트는 임시 폴더에서 YOLO를 짧게 학습하고 MLflow 모델로 저장한 뒤 다시 읽어 추론한다. 환경 변수를 지정하지 않으면 건너뛴다.

```powershell
$env:ML_LABS_RUN_VISION = "1"
uv run --locked --extra dev --extra vision pytest -q -p no:warnings tests\test_vision.py
Remove-Item Env:ML_LABS_RUN_VISION
```

실제 출력:

```text
.                                                                        [100%]
1 passed in 12.69s
```

`YOLO_CONFIG_DIR`은 10장의 탐지 서버에서 다시 쓴다. 다른 프로젝트로 이동할 때 `Remove-Item Env:YOLO_CONFIG_DIR -ErrorAction SilentlyContinue`로 지운다.

**완료 확인**

- [ ] `book-card-baseline`과 `book-card-yolo`가 모두 버전 1로 등록됐다.
- [ ] `best.pt`, `results.png`, `val_batch0_pred.jpg`가 생겼다.
- [ ] 비전 테스트가 `1 passed`다. `skipped`는 검증 성공이 아니다.
- [ ] 합성 데이터의 10 epoch IoU를 실제 신분증 환경의 mAP 인증으로 해석하지 않는다.

## 9장. 추천 후보를 검증 데이터로 선택한다 {#chapter-09}

4장의 테스트 결과를 모델 선택에 다시 쓰지 않는다. 새 seed로 만든 데이터에서 rank 2와 4를 학습하고, 검증 지표만으로 하나를 고른 뒤 그 후보만 테스트한다.

### 9-1. 새 데이터에서 두 후보를 학습한다

**터미널 A, 기본 환경.**

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs movies prepare --output "$W\data\movies-ch09" --seed 43
uv run --locked --extra dev ml-labs movies train --data "$W\data\movies-ch09" --output "$W\runs\movies-rank2" --work "$W\tracking" --rank 2
uv run --locked --extra dev ml-labs movies train --data "$W\data\movies-ch09" --output "$W\runs\movies-rank4" --work "$W\tracking" --rank 4
```

실제 출력:

```text
{
  "result": ".ml-labs\\book-01\\data\\movies-ch09"
}
{
  "result": ".ml-labs\\book-01\\runs\\movies-rank2\\candidate.json"
}
{
  "result": ".ml-labs\\book-01\\runs\\movies-rank4\\candidate.json"
}
```

### 9-2. 검증 NDCG와 RMSE로 후보를 고른다

**터미널 A.** 검증 NDCG@5가 높은 후보를 우선하고, 같으면 검증 RMSE가 낮은 후보를 고른다. 선택 경로는 파일로 남겨 다음 장과 다른 터미널에서 같은 후보를 쓴다.

```powershell
$paths = @("$W\runs\movies-rank2\candidate.json", "$W\runs\movies-rank4\candidate.json")
$ranked = $paths | ForEach-Object {
    $candidate = Get-Content $_ -Raw | ConvertFrom-Json
    [pscustomobject]@{
        Path = $_
        NDCG = $candidate.metrics.validation_model_ndcg_at_5
        RMSE = $candidate.metrics.validation_rmse
    }
} | Sort-Object @{Expression = "NDCG"; Descending = $true}, @{Expression = "RMSE"; Ascending = $true}
$ranked | Format-Table -AutoSize
$MovieCandidate = $ranked[0].Path
$MovieCandidate | Set-Content "$W\selected-movie-path.txt" -Encoding utf8
```

실제 출력:

```text
Path                                              NDCG RMSE
----                                              ---- ----
.ml-labs\book-01\runs\movies-rank2\candidate.json 0.50 0.68
.ml-labs\book-01\runs\movies-rank4\candidate.json 0.40 0.67
```

rank 2의 검증 NDCG는 0.5036, rank 4는 0.4000이다. RMSE는 rank 4가 0.6699로 rank 2의 0.6786보다 조금 낮지만 순위 품질을 우선하는 규칙에 따라 rank 2를 고른다. 평점 오차와 추천 순위는 다른 질문이며, 어떤 지표를 우선할지는 학습 전에 정해 둔다.

### 9-3. 선택한 후보만 평가하고 등록한다

**터미널 A.** 테스트 분할은 선택 뒤 한 번만 연다. 평가가 실패하면 여기서 멈춘다.

```powershell
uv run --locked --extra dev ml-labs movies evaluate --candidate $MovieCandidate --data "$W\data\movies-ch09" --report "$W\reports\movie-selected.json"
$LASTEXITCODE
uv run --locked --extra dev ml-labs register --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --name book-movie-selected
```

실제 출력(판정 부분):

```text
    "passed": true,
      "test_recall_at_5": 0.6666666666666666,
    "observed_validation_rmse": 0.6786069439813943,
      "observed_lift": 0.21742120054652125,
      "passed": true
0
Successfully registered model 'book-movie-selected'.
Created version '1' of model 'book-movie-selected'.
  "registered_uri": "models:/book-movie-selected/1"
```

### 9-4. MLflow에서 선택 근거를 확인한다

**브라우저 C.** MLflow UI를 새로고침하면 지금까지의 run 다섯 개와 등록 모델이 함께 보인다. `book-movie-selected`가 붙은 run이 rank 2 후보다.

![MLflow run 목록. book-card-yolo, rank 4 후보(pyfunc), book-movie-selected, book-card-baseline, book-movie가 붙은 run 다섯 개가 보인다.](/images/ml-platform-engineering/guide/guide-ch09-mlflow-runs.png)

![선택한 rank 2 run의 Parameters와 Metrics. rank 2와 validation_model_ndcg_at_5 0.5036, validation_rmse 0.6786, test_recall_at_5 0.667이 보인다.](/images/ml-platform-engineering/guide/guide-ch09-mlflow-selected-run.png)

![Registered Models 목록. book-card-baseline, book-card-yolo, book-movie, book-movie-selected 네 모델이 모두 Version 1과 champion 별칭을 가진다.](/images/ml-platform-engineering/guide/guide-ch09-mlflow-registry.png)

이 모델은 SVD 추천 구현이다. RMSE는 평점 오차이고 Recall과 NDCG는 추천 순위의 다른 측면이다. 검증 순위 사용자가 5명뿐이라 지표의 분산이 크다는 점도 함께 읽는다. 책의 모든 추천 알고리즘과 대규모 학습을 재현한 것은 아니다. MLflow UI는 여기서 터미널 B의 `Ctrl+C`로 종료해도 된다.

**완료 확인**

- [ ] 선택 이유가 테스트가 아닌 검증 지표에 있다.
- [ ] `selected-movie-path.txt`에 rank 2 후보 경로가 있다.
- [ ] `models:/book-movie-selected/1`이 등록됐다.

## 10장. 출시, 요청과 배치 재처리를 연결한다 {#chapter-10}

선택 후보를 출시 기록으로 고정하고, 온라인 요청과 배치 처리가 같은 출시를 쓰는지 확인한다. 탐지 모델도 같은 방식으로 서빙한다.

### 10-1. 선택 후보를 출시 기록으로 묶는다

**터미널 A, 기본 환경.** 출시 기록은 후보, 평가 보고서 해시와 데이터 지문을 하나의 `release_id`로 묶는다.

```powershell
$MovieCandidate = (Get-Content "$W\selected-movie-path.txt" -Raw).Trim()
uv run --locked --extra dev ml-labs release activate --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --store "$W\movie-releases"
uv run --locked --extra dev ml-labs release show --store "$W\movie-releases"
```

실제 출력(`release show`의 끝부분):

```text
{
  "candidate": {
    "task": "movies",
    "run_id": "a260879e6a8a449b955a6cf19ac316d0",
    ...
    "registered_uri": "models:/book-movie-selected/1"
  },
  "report_sha256": "f54cd82f8224ea5ac4932708798020e748ec947c0463d99f18c549e3c284d6b1",
  "dataset_sha256": "8e9118d658ca4acb4d1898662df0a296b958692bc69b2eff1b6815d2fbb6cc7e",
  "release_id": "5a919a1c3045fc007f7148f5a624702cb0c20998a4e23b7856f7b6badf5e08c3"
}
```

`activate` 출력에는 같은 내용과 `"changed": true`가 붙는다.

### 10-2. 출시 기록으로 서버를 켠다

**터미널 B, 기본 환경.**

```powershell
Set-Location $HOME\ml-labs-book\ml-platform-engineering-labs
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
Remove-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue
uv run --locked --extra dev ml-labs serve --movie-release "$W\movie-releases" --host 127.0.0.1 --port 8000
```

이 영화 서버는 시작할 때 출시 기록의 모델을 고정한다. 출시 포인터를 바꿔도 실행 중인 모델이 자동으로 바뀌지 않으며, 바꾸려면 서버를 다시 시작한다.

### 10-3. 응답에 출시 ID가 붙는지 확인한다

**터미널 A.**

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 6
$body = @{ user_id = "u000" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/recommend -Method Post -ContentType application/json -Body $body | ConvertTo-Json -Depth 6
```

실제 출력(일부):

```text
{
  "status": "ok",
  "models": { "cards": false, "movies": true, "rag": false },
  "movie_release_id": "5a919a1c3045fc007f7148f5a624702cb0c20998a4e23b7856f7b6badf5e08c3",
  ...
}
{
  "user_id": "u000",
  "status": "personalized",
  "recommendations": [
    { "item_id": "m022", "score": 3.405480632014961 },
    { "item_id": "m005", "score": 3.279502309118273 },
    ...
  ],
  "feature_routing": null,
  "model_uri": "models:/book-movie-selected/1",
  "release_id": "5a919a1c3045fc007f7148f5a624702cb0c20998a4e23b7856f7b6badf5e08c3"
}
```

6장과 같은 사용자지만 모델이 바뀌어 추천이 다르다. **브라우저 C**의 `http://127.0.0.1:8000/docs`에서 같은 요청을 실행하면 응답 끝에 `release_id`가 보인다.

![출시 기록으로 띄운 서버의 Swagger 응답. user_id u000의 추천과 model_uri models:/book-movie-selected/1, release_id 5a919a1c로 시작하는 값이 보인다.](/images/ml-platform-engineering/guide/guide-ch10-api-release.png)

서버는 11장의 `/metrics` 확인까지 켜 둔다.

### 10-4. 배치를 실패시키고 같은 업무 키로 다시 실행한다

**터미널 A.** 사용자 파일과 업무 키(`job-key`)를 함께 넘긴다. 첫 실행은 추론 뒤 게시 직전에 일부러 실패한다.

```powershell
@("user_id", "u000", "new-user") | Set-Content "$W\batch-users.csv" -Encoding utf8
uv run --locked --extra dev ml-labs batch --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --users "$W\batch-users.csv" --output "$W\batch-results" --job-key book-day-01 --fail-before-commit
$LASTEXITCODE
Get-ChildItem "$W\batch-results" -Recurse -File
```

실제 출력:

```text
ml-labs: error: Injected failure after inference, before batch publication.
2
```

실패 뒤 `batch-results`에는 게시된 파일이 없다. 이제 실패 옵션만 빼고 같은 작업을 두 번 실행한다.

```powershell
uv run --locked --extra dev ml-labs batch --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --users "$W\batch-users.csv" --output "$W\batch-results" --job-key book-day-01
uv run --locked --extra dev ml-labs batch --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --users "$W\batch-users.csv" --output "$W\batch-results" --job-key book-day-01
```

실제 출력:

```text
{
  "output": ".ml-labs\\book-01\\batch-results\\130bd3280be6ec957d458e7d8bc0dd495362c82053fbc8f4f8a9e5fd8900b892",
  "reused": false,
  "identity": {
    "job_key": "book-day-01",
    "model_uri": "models:/book-movie-selected/1",
    "users_sha256": "753bea19c4ac45477e724eefe22c10621c17d9258ad7774a11d6de6437ac501d",
    "dataset_sha256": "8e9118d658ca4acb4d1898662df0a296b958692bc69b2eff1b6815d2fbb6cc7e",
    ...
  },
  "rows": 2,
  "output_sha256": "fbbe21abf540f1739a4a7c8f766a91f2fb28cd8d76cf7f7191d86a8a89bffd8c"
}
{
  "output": ".ml-labs\\book-01\\batch-results\\130bd3280be6ec957d458e7d8bc0dd495362c82053fbc8f4f8a9e5fd8900b892",
  "reused": true,
  ...
  "output_sha256": "fbbe21abf540f1739a4a7c8f766a91f2fb28cd8d76cf7f7191d86a8a89bffd8c"
}
```

두 번째 실행은 `reused: true`이고 출력 해시가 같다. 같은 업무 키에 다른 사용자 파일을 넘기면 거절된다.

```powershell
@("user_id", "u001") | Set-Content "$W\batch-users-other.csv" -Encoding utf8
uv run --locked --extra dev ml-labs batch --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --users "$W\batch-users-other.csv" --output "$W\batch-results" --job-key book-day-01
```

실제 출력:

```text
ml-labs: error: Business job key already belongs to different inputs or model.
```

결과 파일 `predictions.json`에는 모델 입력에서 뺀 `user_id`가 응답마다 다시 붙어 누구의 예측인지 남는다. 이는 단일 호스트 파일시스템 실험이며 분산 저장소 transaction이나 KServe 무중단 전환을 구현한 것은 아니다.

### 10-5. 탐지 모델 서버를 켠다

**터미널 B2(새 창), vision 환경.** 추천 서버와 포트를 나눠 8002번에 띄운다.

```powershell
Set-Location $HOME\ml-labs-book\ml-platform-engineering-labs
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-vision"
$env:YOLO_CONFIG_DIR = (Resolve-Path "$W\yolo-config").Path
Remove-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue
uv run --locked --extra vision ml-labs serve --cards "$W\runs\cards-yolo\candidate.json" --host 127.0.0.1 --port 8002
```

### 10-6. 카드가 있는 이미지와 없는 이미지를 요청한다

**터미널 A.** 테스트의 첫 이미지 `test-0000`은 라벨이 빈 음성 표본이고 `test-0001`에는 카드가 있다.

```powershell
foreach ($name in "test-0000", "test-0001") {
    $body = @{ image_path = "$W\data\cards\images\test\$name.png" } | ConvertTo-Json
    Invoke-RestMethod http://127.0.0.1:8002/predict/cards -Method Post -ContentType application/json -Body $body | ConvertTo-Json -Depth 6
}
Get-Content "$W\data\cards\labels\test\test-0001.txt"
```

실제 출력:

```text
{
  "image_path": ".ml-labs\\book-01\\data\\cards\\images\\test\\test-0000.png",
  "detected": false,
  "box_xyxy": null,
  "backend": "yolov8"
}
{
  "image_path": ".ml-labs\\book-01\\data\\cards\\images\\test\\test-0001.png",
  "detected": true,
  "box_xyxy": [
    28.966873168945312,
    14.083757400512695,
    82.9388427734375,
    62.413665771484375
  ],
  "backend": "yolov8"
}
0 0.433594 0.296875 0.429688 0.375000
```

라벨을 128픽셀 좌표로 바꾸면 x 28.0~83.0, y 14.0~62.0이다. 예측 상자와 거의 겹친다. **브라우저 C**의 `http://127.0.0.1:8002/docs`에서도 같은 요청을 보낼 수 있다.

![탐지 서버 Swagger의 POST /predict/cards 응답. test-0001.png에 대해 detected true, box_xyxy 네 좌표와 backend yolov8이 반환됐다.](/images/ml-platform-engineering/guide/guide-ch10-card-detect.png)

이 엔드포인트는 서버가 실행 중인 컴퓨터의 파일 경로를 읽는 로컬 실습용이며 이미지 업로드 API가 아니다. 다른 호스트나 공개 서비스에 경로 입력을 그대로 노출하지 않는다. 확인 뒤 터미널 B2에서 `Ctrl+C`로 탐지 서버만 종료한다.

**완료 확인**

- [ ] 추천 응답의 `release_id`가 `release show`의 값과 같다.
- [ ] 실패 주입 뒤 게시 파일이 없고, 재실행 두 번째에 `reused: true`가 나온다.
- [ ] 같은 업무 키에 다른 입력을 넘기면 거절된다.
- [ ] 탐지 응답의 `backend`가 `yolov8`이고 음성 표본에서는 `box_xyxy`가 `null`이다.

## 11장. 서비스 상태와 데이터 변화를 따로 관측한다 {#chapter-11}

요청 수와 지연 같은 서비스 지표, 입력 분포 변화, 그리고 장애 복구 증거는 서로 다른 질문에 답한다. 셋을 따로 확인한다.

### 11-1. `/metrics`의 요청 카운터를 확인한다

**터미널 A, 10장의 추천 서버(8000번)가 켜진 상태.**

```powershell
(Invoke-WebRequest http://127.0.0.1:8000/metrics).Content -split "`n" | Select-String "ml_labs_inference_requests_total\{|ml_labs_inference_seconds_count"
$body = @{ user_id = "new-user" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/recommend -Method Post -ContentType application/json -Body $body | Out-Null
(Invoke-WebRequest http://127.0.0.1:8000/metrics).Content -split "`n" | Select-String "ml_labs_inference_requests_total\{|ml_labs_inference_seconds_count"
```

실제 출력:

```text
ml_labs_inference_requests_total{status="success",task="movies"} 2.0
ml_labs_inference_seconds_count{task="movies"} 2.0
ml_labs_inference_requests_total{status="success",task="movies"} 3.0
ml_labs_inference_seconds_count{task="movies"} 3.0
```

전체 응답에는 `ml_labs_inference_seconds_bucket`처럼 지연 히스토그램도 들어 있다. 이것은 Prometheus 형식의 계측이며 Prometheus, Grafana와 Alertmanager 설치 성공은 아니다. 확인 뒤 터미널 B의 추천 서버를 `Ctrl+C`로 종료한다.

### 11-2. 분포가 바뀐 비교 파일로 드리프트를 계산한다

**터미널 A, tools 환경.** 원본 데이터는 바꾸지 않고 기준(reference)과 현재(current) 파일을 따로 만든다. 현재 파일은 평점을 모두 1.0으로 바꿔 분포를 일부러 무너뜨린다.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-tools"
uv run --locked --extra monitor python -c "import sys,pandas as pd; d=pd.read_csv(sys.argv[1]); d[['rating']].to_csv(sys.argv[2],index=False); d['rating']=1.0; d[['rating']].to_csv(sys.argv[3],index=False)" "$W\data\movies\ratings.csv" "$W\reference.csv" "$W\current.csv"
uv run --locked --extra monitor ml-labs tools drift --reference "$W\reference.csv" --current "$W\current.csv" --output "$W\reports\drift.json" --backend evidently
Get-Content "$W\reports\drift.json" -TotalCount 12
```

실제 출력(NumPy 경고 생략):

```text
{
  "backend": "evidently",
  "html_report": ".ml-labs\\book-01\\reports\\drift.html",
  "json_report": ".ml-labs\\book-01\\reports\\drift.json",
  "reference_rows": 864,
  "current_rows": 864,
  "monitoring_note": "Drift is a signal, not proof of model failure."
}
{
  "metrics": [
    {
      "metric": "DatasetDriftMetric",
      "result": {
        "drift_share": 0.5,
        "number_of_columns": 1,
        "number_of_drifted_columns": 1,
        "share_of_drifted_columns": 1.0,
        "dataset_drift": true
      }
```

`return c / c` 같은 NumPy 경고는 현재 분포의 분산이 0이라 생기며 결과에는 영향이 없다.

### 11-3. Evidently 보고서를 연다

**브라우저 C.**

```powershell
Start-Process "$W\reports\drift.html"
```

![Evidently Dataset Drift 보고서. rating 열 1개에서 드리프트가 감지됐고 K-S p_value 기준 drift score 0, 기준 분포는 종 모양이고 현재 분포는 막대 하나다.](/images/ml-platform-engineering/guide/guide-ch11-evidently-drift.png)

보고서는 실제 Evidently 0.4.40이 계산한 결과다. 변화한 입력 분포와 모델 정확도는 다른 증거이므로 자동 재학습으로 바로 연결하지 않는다. 정답 레이블, 수집 오류와 업무 영향을 추가로 확인한다.

### 11-4. 피처 장애, 배치 재시도와 출시 복구를 한 번에 재연한다

**터미널 A, tools 환경.** 통합 실험은 새 폴더에서 Feast 피처 공급 전후의 요청, 배치 재시도, 출시 교체와 복구, 드리프트 보고서를 차례로 실행하고 증거를 `evidence.json`에 남긴다.

```powershell
uv run --locked --extra dev --extra feast --extra monitor ml-labs exercise --work "$W\integrated"
$evidence = Get-Content "$W\integrated\evidence.json" -Raw | ConvertFrom-Json
$evidence.feature_failure_http
$evidence.feature_recovery.status
$evidence.batch.retried.reused
$evidence.releases | ConvertTo-Json
```

실제 출력(마지막 네 명령):

```text
503
personalized
True
{
  "first": "1fb36b3ba8a00771dc1863f3f60dab5f9b77153a5aab309fd44034fe2d1a4f59",
  "next": "198edac9ab7e89958a7bb0a2d4dad6e332280e99aeecd8318d720372eab95b0e",
  "restored": "1fb36b3ba8a00771dc1863f3f60dab5f9b77153a5aab309fd44034fe2d1a4f59"
}
```

피처 공급 전에는 HTTP 503, 공급 후에는 개인화 응답, 배치 재시도는 재사용, 출시는 다음 버전으로 바꿨다가 최초 `release_id`로 복구됐다. 실행은 약 11초가 걸렸다. [통합 실험의 개별 단계](/docs/tech/ops/mlops/labs/ml-platform-labs-09-integrated-operations/)에는 각 실패를 직접 주입하는 절차가 있다.

**완료 확인**

- [ ] 요청 하나에 `ml_labs_inference_requests_total`이 1 증가했다.
- [ ] `drift.json`의 `dataset_drift`가 `true`이고 HTML 보고서가 열린다.
- [ ] `evidence.json`에서 503, `personalized`, `True`, `first`와 `restored`가 같은 값이 나온다.
- [ ] Eigen-CAM, EMF와 Deepchecks 등 책의 설명가능성, 검사 도구 전체는 이 실행에 포함되지 않는다.

## 12장. 같은 문서와 설정으로 검색과 응답을 만든다 {#chapter-12}

RAG 후보를 모델처럼 다룬다. 문서, 검색 설정, 프롬프트와 평가 집합을 해시로 고정한 후보를 만들고, 평가를 통과한 후보만 출시 저장소에 활성화한다.

### 12-1. 공개 합성 문서와 설정을 만든다

**터미널 A, 기본 환경.**

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs rag release init-demo --output "$W\rag\inputs"
Get-Content "$W\rag\inputs\config.json"
Get-Content "$W\rag\inputs\evaluation.json"
```

실제 출력:

```text
{
  "corpus": ".ml-labs\\book-01\\rag\\inputs\\documents.jsonl",
  "config": ".ml-labs\\book-01\\rag\\inputs\\config.json",
  "prompt": ".ml-labs\\book-01\\rag\\inputs\\prompt.json",
  "evaluation": ".ml-labs\\book-01\\rag\\inputs\\evaluation.json"
}
{"min_score":0.15,"ngram_range":[1,2],"provider":"extractive_offline","retriever":"tfidf","stop_words":"english","top_k":2}
[{"answer_contains":["validation"],"expected_ids":["doc-mlflow-registry"],"id":"registry","query":"model registry champion promotion"},{"answer_contains":["historical"],"expected_ids":["doc-feast"],"id":"features","query":"Feast offline online feature store"},{"id":"unknown","query":"quasar teleportation warranty","unanswerable":true}]
```

평가 집합은 답해야 할 질문 두 개와 답하지 말아야 할 질문 하나로 이루어진다. 답할 수 없는 질문을 넣어야 근거 없이 답을 지어내는 후보를 걸러낼 수 있다.

### 12-2. 후보를 만들고 평가한 뒤 활성화한다

**터미널 A.** 평가 출력은 사례별 응답이 길게 나오므로 `Out-Null`로 숨기고 보고서의 판정만 읽는다. 오류 메시지는 그대로 보인다.

```powershell
uv run --locked --extra dev ml-labs rag release create --corpus "$W\rag\inputs\documents.jsonl" --config "$W\rag\inputs\config.json" --prompt "$W\rag\inputs\prompt.json" --evaluation "$W\rag\inputs\evaluation.json" --output "$W\rag\v1"
uv run --locked --extra dev ml-labs rag release evaluate --candidate "$W\rag\v1\candidate.json" --report "$W\rag\v1-report.json" | Out-Null
$LASTEXITCODE
(Get-Content "$W\rag\v1-report.json" -Raw | ConvertFrom-Json).summary | ConvertTo-Json
uv run --locked --extra dev ml-labs rag release activate --store "$W\rag\store" --candidate "$W\rag\v1\candidate.json" --report "$W\rag\v1-report.json"
```

실제 출력:

```text
{
  "candidate": ".ml-labs\\book-01\\rag\\v1\\candidate.json"
}
0
{
  "baseline_pass_rate": null,
  "cost_usd": 0,
  "input_tokens": null,
  "p95_latency_ms": 0.5670300015481189,
  "pass_rate": 1.0,
  "regressions": []
}
{
  "schema": "ml-labs-rag-release-v1",
  "candidate_id": "2ddd1503bb9756432d1b16e5fe3c8d7dc02ad5bdb1c8405f42572012ed354cca",
  "report_id": "0a93924f947130bf929b1471161db04a433f5edfab1d3e3e3d1d030086addf2b",
  "release_id": "bbe0e50fce4a0e8176aae32e641466553121f3398be34174581529af55879017"
}
```

`release_id` 앞부분(`bbe0e50f`)을 기록해 둔다. 13장에서 이 값으로 돌아오는지 확인한다.

### 12-3. 근거가 있는 질문과 없는 질문을 비교한다

**터미널 A.**

```powershell
uv run --locked --extra dev ml-labs rag release query --store "$W\rag\store" --query "model registry champion promotion"
uv run --locked --extra dev ml-labs rag release query --store "$W\rag\store" --query "quasar teleportation warranty"
```

실제 출력(지표 일부 생략):

```text
{
  "query": "model registry champion promotion",
  "answer": "[doc-mlflow-registry] A model registry versions named models and supports aliases such as champion. A candidate should pass validation before promotion and deployment.",
  "citations": [ "doc-mlflow-registry" ],
  "retrieved": [ { "id": "doc-mlflow-registry", "title": "Model registry and promotion", "score": 0.42757112043785056, ... } ],
  "abstained": false,
  "citations_valid": true,
  "status": "answered",
  "answer_mode": "extractive_offline",
  "metrics": { "llm_calls": 0, "cost_usd": 0.0, "usage_source": "no_model_called", ... },
  "candidate_id": "2ddd1503bb9756432d1b16e5fe3c8d7dc02ad5bdb1c8405f42572012ed354cca",
  "release_id": "bbe0e50fce4a0e8176aae32e641466553121f3398be34174581529af55879017"
}
{
  "query": "quasar teleportation warranty",
  "answer": "No grounded answer is available in the selected corpus.",
  "citations": [],
  "retrieved": [],
  "abstained": true,
  "citations_valid": true,
  "status": "no_grounding",
  ...
  "release_id": "bbe0e50fce4a0e8176aae32e641466553121f3398be34174581529af55879017"
}
```

기본 provider는 `extractive_offline`이다. TF-IDF로 찾은 문장을 그대로 인용하며 LLM을 호출하지 않는다(`llm_calls: 0`). 이를 책의 Gemini, FAISS, LangChain과 Chainlit 구현 완료로 표시하지 않는다.

### 12-4. 실제 생성 모델 연결은 선택 경로로 남긴다

기존 Azure OpenAI를 쓰는 독립 생성 경로는 [RAG 출시 가이드의 생성 연결](/docs/tech/ops/mlops/labs/ml-platform-labs-10-rag-release/)에 있다. 기존 endpoint, 배포 이름, 인증과 예산이 필요하며, 책의 Gemini 실행과 같은 도구도 아니다. 이 판에서는 외부 생성 요청을 보내지 않았다.

생성 모드를 켤 때는 고정한 검색 결과와 프롬프트가 실제 요청에 쓰였는지, 인용이 검색된 문서 안에 있는지 확인한다. 형식 검사 통과가 답변의 모든 주장이 사실이라는 증거는 아니다. 키가 없는 상태에서 가짜 생성 결과를 넣어 통과시키지 않는다.

**완료 확인**

- [ ] v1 평가의 `pass_rate`가 1.0이다.
- [ ] 첫 질문은 `answered`와 인용 하나, 두 번째는 `no_grounding`과 빈 인용이다.
- [ ] 두 응답의 `release_id`가 활성화 출력과 같다.

## 13장. 변경을 평가하고 출시를 거절하거나 되돌린다 {#chapter-13}

출시 저장소를 HTTP 서버에 연결해 두고 나쁜 변경의 거절, 좋은 변경의 활성화, 이전 버전 복구가 실제 응답에 어떻게 반영되는지 본다.

### 13-1. RAG 서버를 켜고 현재 출시를 확인한다

**터미널 B, 기본 환경.** 이 서버는 요청마다 활성 스냅샷을 다시 읽는다. 10장의 추천 서버처럼 시작할 때 고정하지 않는다.

```powershell
Set-Location $HOME\ml-labs-book\ml-platform-engineering-labs
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
Remove-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue
uv run --locked --extra dev ml-labs serve --rag-release "$W\rag\store" --host 127.0.0.1 --port 8003
```

**터미널 A.** 이후 단계에서 반복해 쓸 확인 함수를 만든다.

```powershell
function Show-RagRelease {
    $body = @{ query = "model registry champion promotion" } | ConvertTo-Json
    Invoke-RestMethod http://127.0.0.1:8003/rag/query -Method Post -ContentType application/json -Body $body |
        Select-Object status, release_id, candidate_id, @{ n = "citations"; e = { $_.citations -join "," } } |
        Format-List
}
Show-RagRelease
```

실제 출력:

```text
status       : answered
release_id   : bbe0e50fce4a0e8176aae32e641466553121f3398be34174581529af55879017
candidate_id : 2ddd1503bb9756432d1b16e5fe3c8d7dc02ad5bdb1c8405f42572012ed354cca
citations    : doc-mlflow-registry
```

**브라우저 C**의 `http://127.0.0.1:8003/docs`에서 `POST /rag/query`에 같은 질문을 보내면 전체 응답과 끝의 `release_id`를 볼 수 있다.

![RAG 서버 Swagger의 POST /rag/query 응답. answered 상태, doc-mlflow-registry 인용, llm_calls 0, candidate_id 2ddd1503과 release_id bbe0e50f로 시작하는 값이 보인다.](/images/ml-platform-engineering/guide/guide-ch13-rag-http-v1.png)

### 13-2. 검색 임계치를 잘못 올린 후보는 거절된다

**터미널 A, 기본 환경.** 원본 v1은 그대로 두고 `min_score`를 1.0으로 올린 후보를 만든다. 통과율 기준을 0.3으로 느슨하게 해도 v1이 답하던 사례를 잃으면 회귀 게이트(`--max-regression 0`)가 막는다.

```powershell
$badConfig = Get-Content "$W\rag\inputs\config.json" -Raw | ConvertFrom-Json
$badConfig.min_score = 1.0
$badConfig | ConvertTo-Json -Depth 10 | Set-Content "$W\rag\bad-config.json" -Encoding utf8
uv run --locked --extra dev ml-labs rag release create --corpus "$W\rag\inputs\documents.jsonl" --config "$W\rag\bad-config.json" --prompt "$W\rag\inputs\prompt.json" --evaluation "$W\rag\inputs\evaluation.json" --output "$W\rag\bad"
uv run --locked --extra dev ml-labs rag release evaluate --candidate "$W\rag\bad\candidate.json" --baseline "$W\rag\v1\candidate.json" --min-pass-rate 0.3 --max-regression 0 --report "$W\rag\bad-report.json" | Out-Null
$LASTEXITCODE
(Get-Content "$W\rag\bad-report.json" -Raw | ConvertFrom-Json).summary | ConvertTo-Json
uv run --locked --extra dev ml-labs rag release activate --store "$W\rag\store" --candidate "$W\rag\bad\candidate.json" --report "$W\rag\bad-report.json"
$LASTEXITCODE
Show-RagRelease
```

실제 출력:

```text
{
  "candidate": ".ml-labs\\book-01\\rag\\bad\\candidate.json"
}
ml-labs: error: RAG release gate failed; report: .ml-labs\book-01\rag\bad-report.json
2
{
  "baseline_pass_rate": 1.0,
  "cost_usd": 0,
  "input_tokens": null,
  "p95_latency_ms": 0.6132099995738827,
  "pass_rate": 0.3333333333333333,
  "regressions": [
    "registry",
    "features"
  ]
}
ml-labs: error: RAG release gate failed; activation refused.
2

status       : answered
release_id   : bbe0e50fce4a0e8176aae32e641466553121f3398be34174581529af55879017
candidate_id : 2ddd1503bb9756432d1b16e5fe3c8d7dc02ad5bdb1c8405f42572012ed354cca
citations    : doc-mlflow-registry
```

통과율 0.33은 기준 0.3을 넘지만 `registry`, `features` 두 사례가 회귀해 실패했다. 활성화도 거절되고 HTTP 응답은 여전히 v1(`bbe0e50f`)이다.

### 13-3. 정상 변경을 평가하고 활성화한다

**터미널 A.** `top_k`를 3으로 늘린 v2를 만들고 v1을 기준으로 평가한다.

```powershell
$v2Config = Get-Content "$W\rag\inputs\config.json" -Raw | ConvertFrom-Json
$v2Config.top_k = 3
$v2Config | ConvertTo-Json -Depth 10 | Set-Content "$W\rag\v2-config.json" -Encoding utf8
uv run --locked --extra dev ml-labs rag release create --corpus "$W\rag\inputs\documents.jsonl" --config "$W\rag\v2-config.json" --prompt "$W\rag\inputs\prompt.json" --evaluation "$W\rag\inputs\evaluation.json" --output "$W\rag\v2"
uv run --locked --extra dev ml-labs rag release evaluate --candidate "$W\rag\v2\candidate.json" --baseline "$W\rag\v1\candidate.json" --report "$W\rag\v2-report.json" | Out-Null
$LASTEXITCODE
uv run --locked --extra dev ml-labs rag release activate --store "$W\rag\store" --candidate "$W\rag\v2\candidate.json" --report "$W\rag\v2-report.json"
Show-RagRelease
```

실제 출력:

```text
{
  "candidate": ".ml-labs\\book-01\\rag\\v2\\candidate.json"
}
0
{
  "schema": "ml-labs-rag-release-v1",
  "candidate_id": "6c6f8ff9ba9ab661af59a6a11fbf8619b0ed244c885245675fe034820b35f82d",
  "report_id": "761e2bff9c666bc49fda865c6884afa8dc0346c76a59be270334f6efdf5929d3",
  "release_id": "4dd49e008aa1847487f340a458a89bace725d6a8290b223e8fc6374f06c56c01"
}

status       : answered
release_id   : 4dd49e008aa1847487f340a458a89bace725d6a8290b223e8fc6374f06c56c01
candidate_id : 6c6f8ff9ba9ab661af59a6a11fbf8619b0ed244c885245675fe034820b35f82d
citations    : doc-mlflow-registry
```

서버를 다시 시작하지 않았는데 HTTP 응답의 `release_id`가 `4dd49e00`로 바뀌었다.

### 13-4. 이전 출시로 되돌린다

**터미널 A.**

```powershell
uv run --locked --extra dev ml-labs rag release rollback --store "$W\rag\store"
Show-RagRelease
```

실제 출력:

```text
{
  "candidate_id": "2ddd1503bb9756432d1b16e5fe3c8d7dc02ad5bdb1c8405f42572012ed354cca",
  "release_id": "bbe0e50fce4a0e8176aae32e641466553121f3398be34174581529af55879017",
  "report_id": "0a93924f947130bf929b1471161db04a433f5edfab1d3e3e3d1d030086addf2b",
  "schema": "ml-labs-rag-release-v1"
}

status       : answered
release_id   : bbe0e50fce4a0e8176aae32e641466553121f3398be34174581529af55879017
candidate_id : 2ddd1503bb9756432d1b16e5fe3c8d7dc02ad5bdb1c8405f42572012ed354cca
citations    : doc-mlflow-registry
```

응답이 v1의 `bbe0e50f`로 돌아왔다. 후보의 평균 점수가 좋다는 주장과 실제 서버가 그 후보로 응답한다는 증거는 다르다. 이 단계는 후자를 확인한다. 확인 뒤 터미널 B에서 `Ctrl+C`로 서버를 종료한다.

### 13-5. Promptfoo로 활성 후보를 직접 호출해 검사한다

**터미널 A, 기본 환경.** Promptfoo 설정은 v1 후보를 실제로 호출하는 Python provider를 가리킨다. 별도 예제 프롬프트를 평가하는 것이 아니다. `PROMPTFOO_CONFIG_DIR`을 실습 폴더로 지정하면 결과 DB가 다른 프로젝트와 섞이지 않는다.

```powershell
uv run --locked --extra dev ml-labs tools promptfoo release-config --candidate "$W\rag\v1\candidate.json" --output "$W\rag\promptfoo.yaml"
$env:PROMPTFOO_PYTHON = (Resolve-Path "$env:UV_PROJECT_ENVIRONMENT\Scripts\python.exe").Path
$env:PROMPTFOO_DISABLE_TELEMETRY = "1"
$env:PROMPTFOO_CONFIG_DIR = Join-Path (Resolve-Path $W).Path "promptfoo-home"
npm exec --yes --package=promptfoo@0.125.0 -- promptfoo eval --config "$W\rag\promptfoo.yaml" --no-cache --output "$W\rag\promptfoo-results.json"
```

실제 출력(버전 안내 상자 생략):

```text
{
  "config": ".ml-labs\\book-01\\rag\\promptfoo.yaml"
}
Cache is disabled.
Starting evaluation eval-JnZ-2026-11-07T12:33:01
Running 3 test cases (up to 4 at a time)...

┌────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────┐
│ query                                                      │ [file://C:\Users\<사용자>\...\ml-platform-engineering-labs… │
│                                                            │ {{query}}                                                  │
├────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
│ model registry champion promotion                          │ [PASS] {"query": "model registry champion promotion",      │
│                                                            │ "answer": "[doc-mlflow-registry] A model registry versions │
│                                                            │ named models and supports aliases such as champion. A      │
│                                                            │ candidate should pass validation before promotion and      │
│                                                            │ deployment.", "citations": ["doc-...                       │
├────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
│ Feast offline online feature store                         │ [PASS] {"query": "Feast offline online feature store",     │
│                                                            │ "answer": "[doc-feast] Feast separates feature definitions │
│                                                            │ from materialized feature values. An offline store         │
│                                                            │ supports historical training retrieval and an online store │
│                                                            │ serves low-latency latest valu...                          │
├────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┤
│ quasar teleportation warranty                              │ [PASS] {"query": "quasar teleportation warranty",          │
│                                                            │ "answer": "No grounded answer is available in the selected │
│                                                            │ corpus.", "citations": [], "retrieved": [], "abstained":   │
│                                                            │ true, "citations_valid": true, "status": "no_grounding",   │
│                                                            │ "answer_mode": "extractive_offl...                         │
└────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────┘
✓ Eval complete (ID: eval-JnZ-2026-11-07T12:33:01)

Results:
  ✓ 3 passed (100%)
  0 failed (0%)
  0 errors (0%)
Duration: 2s (concurrency: 4)

Writing output to .ml-labs\book-01\rag\promptfoo-results.json
```

처음 실행하면 npm이 promptfoo 패키지를 내려받는다. 로컬 인용 후보이므로 유료 생성 API는 호출하지 않는다.

### 13-6. Promptfoo 화면에서 사례별 결과를 본다

**터미널 B, 같은 환경 변수.** 결과 화면 서버를 켠다. `--no`는 브라우저를 자동으로 열지 않는다는 뜻이다.

```powershell
$env:PROMPTFOO_DISABLE_TELEMETRY = "1"
$env:PROMPTFOO_CONFIG_DIR = Join-Path (Resolve-Path $W).Path "promptfoo-home"
npm exec --yes --package=promptfoo@0.125.0 -- promptfoo view --port 15500 --no
```

**브라우저 C.** `http://127.0.0.1:15500`을 연다. 세 사례가 모두 PASS이고 각 출력에 인용과 상태가 보인다.

![Promptfoo 결과 화면. Real RAG snapshot 2ddd1503 평가에서 registry, features, unknown 세 사례가 모두 PASS이고 100% passing 3/3 cases다. 공급자 경로의 사용자 폴더는 가렸다.](/images/ml-platform-engineering/guide/guide-ch13-promptfoo-view.png)

확인 뒤 `Ctrl+C`로 종료한다. 이 결과는 프로젝트의 출시용 평가 보고서를 대신하지 않는다.

### 13-7. DeepEval과 Langfuse는 선택 경로로 남긴다

DeepEval의 의미 평가와 Langfuse 외부 추적은 [별도 연결 절차](/docs/tech/ops/mlops/labs/ml-platform-labs-10-rag-release/)로 진행한다. 판정 모델 키와 외부 서비스 계정이 필요하며 이 판에서는 실행하지 않았다. 연결할 때도 공개 합성 문서와 질문만 전송하고, 실제 요청 성공을 확인하기 전에는 외부 연결 완료로 표시하지 않는다. 의미 캐시, 문서별 권한과 비용 강제 제한은 아직 이 로컬 실행판에 구현되지 않았다.

**완료 확인**

- [ ] 나쁜 후보는 평가와 활성화가 모두 종료 코드 2로 실패하고 HTTP 응답이 v1에 머문다.
- [ ] v2 활성화 직후 HTTP `release_id`가 바뀌고, rollback 뒤 v1 값으로 돌아온다.
- [ ] Promptfoo가 `3 passed (100%)`다.
- [ ] 이 단일 호스트 실험을 조직 승인, 다중 사용자 권한과 종합적인 LLM 안전성 평가로 해석하지 않는다.

## 구현과 검증 범위 {#verification-scope}

이 가이드는 [공개 코드의 고정 커밋](https://github.com/johklo/ml-platform-engineering-labs/tree/ff23b38f88d88268216e2985ff5b6ed0c3defb8c)과 [클러스터 저장소](https://github.com/johklo/ml-platform-book-env)를 기준으로 한다. 원문 명령의 순서를 그대로 복사한 것이 아니라 독립 구현과 책의 실행 참조를 연결했다. 아래 표의 "실행 확인"은 2026년 11월 7일 새 작업 폴더 `.ml-labs\book-01`에서 이 문서의 명령으로 관찰한 결과다.

| 구간 | 이 판에서 실행으로 확인한 것 | 실행하지 않았거나 책 전체 실습 완료에 남은 것 |
| --- | --- | --- |
| 준비, 1장 | 도구 버전 확인, uv 환경 4개 `uv sync --locked`, CLI 실행 | winget 설치 명령과 `git clone`은 이미 설치된 도구와 같은 커밋의 기존 사본으로 대신했다 |
| 2장 | `smoke`의 세 프로젝트 학습, 평가, 등록 | 조직별 책임과 운영 승인 체계 |
| 3장 | Docker 엔진, kind, kubectl, `bookenv.py check`, `status`, 포트포워딩된 KFP 접속 | `bookenv.py up`은 같은 스크립트로 미리 만든 클러스터를 재사용해 다시 실행하지 않았다. 전체 Kubeflow, Notebooks |
| 4장 | 추천 학습, 평가, 거절, 등록, MLflow 화면, 실제 Feast 정의 등록, 과거 조회, 적재 전후 온라인 조회 | 책의 소득 분류 노트북(별도 [실행 참조](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/#book-lab-sop)), Redis 온라인 저장소 |
| 5장 | KFP 컴파일, 컴포넌트 본문 검사, 이미지 빌드, `kind load`, KFP 2.4.1 클러스터 run 성공과 그래프, 지표, 로그 | 컴포넌트에서 클러스터 MLflow와 S3로 기록하는 구성, GitLab CI와 Argo CD 전체 경로 |
| 6장 | FastAPI 개인화와 콜드스타트 응답, BentoML 가져오기, Bento 생성, HTTP 응답(포트 3010) | `bentoml containerize`, Yatai 또는 선택 배포 관리자의 클러스터 출시 |
| 7~9장 | 합성 카드와 MovieLens 가져오기, 색상 기준선, CPU YOLO 10 epoch 학습과 평가, 등록, 비전 재로딩 테스트, 검증 기반 추천 후보 선택과 등록 | 원본 데이터 전체, 책의 학습 알고리즘과 대규모 처리, 표준 mAP 기반 정책 |
| 10~11장 | 출시 기록 기반 추천 서버, 배치 실패 주입과 멱등 재시도, 업무 키 충돌 거절, YOLO 탐지 HTTP, `/metrics`, Evidently 보고서, 통합 실험 증거 | KServe, Prometheus와 Grafana 운영 스택, Deepchecks, Eigen-CAM과 EMF |
| 12~13장 | RAG 후보 생성, 평가, 활성화, 근거 없음 응답, 회귀 후보 거절, HTTP에서 재시작 없는 활성화와 복구, Promptfoo eval과 view | 외부 LLM 생성(Azure OpenAI, Gemini), DeepEval, Langfuse, FAISS, LangChain, Chainlit 원본 경로, 권한과 캐시, 비용 제한 |

같은 날 기본 환경에서 실습 저장소 전체 테스트(`pytest -q`)를 실행해 54개 통과, 8개 건너뜀을 확인했다. 선택 테스트의 `skipped`는 검증 성공이 아니다. 합성 데이터의 10 epoch 학습과 IoU 게이트는 다른 데이터나 실제 촬영 환경의 품질을 보증하지 않는다. 공개 합성 문서에서의 RAG 성공은 실제 업무 문서의 답변 품질을 인증하지 않는다.

이번 실행에서 가이드를 고친 지점은 다음과 같다. KFP 2.4.1 백엔드에 제출하면 평가 작업 driver가 표시 이름 때문에 실패해 5-5의 YAML 정규화 단계를 추가했다. BentoML 기본 저장소를 다른 프로세스가 잠그고 있어 `BENTOML_HOME`을 실습 폴더로 분리했다. `Invoke-RestMethod` 출력에 `ConvertTo-Json`을 붙여 중첩 응답이 그대로 보이게 했다. 탐지 요청은 첫 테스트 이미지가 음성 표본이라 카드가 있는 이미지와 함께 보내도록 바꿨다. MovieLens는 저장소 최상위가 아니라 `$W\downloads`에 받는다.

## 다음 날 다시 시작하고 정리하기

기존 `$W`를 이어 쓸 때는 만들어진 데이터와 후보를 다시 덮어쓰지 않는다. 현재 단계의 입력 파일, 등록 버전과 보고서를 확인한 뒤 다음 명령부터 진행한다. 새 실험은 새 작업 경로를 사용한다.

```powershell
Set-Location $HOME\ml-labs-book\ml-platform-engineering-labs
$W = ".ml-labs\book-01"
Get-ChildItem $W | Select-Object Name
git rev-parse HEAD
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev pytest -q -p no:warnings
```

실제 출력(마지막 줄):

```text
54 passed, 8 skipped in 19.99s
```

API와 UI는 각각의 터미널에서 `Ctrl+C`로 종료한다. 포트포워딩 종료는 클러스터 삭제가 아니다. 클러스터까지 지우려면 `ml-platform-book-env`에서 `uv run --no-project --python 3.12 python bookenv.py down`을 실행한다. 이 명령은 kind 클러스터 안의 모든 실행 기록과 저장소 데이터를 지우므로 다른 사람과 공유하는 클러스터에서는 실행하지 않는다. 실습 결과와 모델의 연결을 확인하기 전에 Tracking DB나 아티팩트만 따로 지우지 않는다.

원리와 책의 차이를 다시 보고 싶다면 [책 해설](/docs/tech/machine-learning-platform-engineering/00-overview/)로, 도구별 상세 실패 실험은 [통합 실습 목차](/docs/tech/ops/mlops/labs/)로 돌아간다.
