---
title: "책 1~13장 순차 실습 가이드"
description: "준비, 실행, 결과 확인과 실패 복구를 한 작업 폴더로 연결하는 ML 플랫폼 로컬 실행판"
date: 2026-11-07T14:00:00+09:00
weight: 1
tags: ["mlops", "ml-platform-engineering", "hands-on", "llmops"]
---

책의 개념을 이해하는 [챕터 해설](/docs/tech/machine-learning-platform-engineering/00-overview/)과 직접 실행하는 과정은 분리했다. 이 가이드는 『Machine Learning Platform Engineering』의 1~13장 순서로 환경, 데이터, 모델, 서비스와 변경 평가를 연결한다. 명령만 실행하는 것이 아니라 각 단계에서 남은 파일을 다음 단계가 어떻게 사용하는지 확인한다.

**현재 판은 실행 가능한 로컬 학습 경로이며, 책의 모든 도구와 원본 실습을 재현한 완성판은 아니다.** MLflow, Feast, KFP 컴포넌트, 실제 CPU YOLO 학습과 Evidently는 실행으로 확인했다. Kubernetes 실행, KServe, 설명가능성 도구 전체와 외부 LLM 서비스는 별도 검증이 남아 있다. 이를 합성 기준선이나 YAML 생성으로 통과 처리하지 않는다. [구현과 검증 범위](#verification-scope)를 먼저 확인한다.

## 시작 전에 정할 것

| 구분 | 준비할 것 | 이 가이드의 기준 |
| --- | --- | --- |
| 기본 실행 | Git, uv, Python 3.11 또는 3.12 | Windows PowerShell, 로컬 CPU |
| 컨테이너와 KFP | 실행 중인 Docker Linux 엔진, kind, kubectl | 별도 `book-env` 학습 클러스터 |
| 탐지 학습 | PyTorch, Ultralytics, 모델 다운로드와 디스크 공간 | 선택 환경에서 실제 YOLO CPU 학습 |
| 외부 생성과 평가 | 기존 모델 배포, 인증, 데이터 전송 허용 범위와 예산 | 명시적으로 선택하는 별도 경로 |
| 작업 보존 | 코드 커밋, 데이터 지문, 모델과 평가 결과 | `.ml-labs\book-01` 아래 보관 |

기본 명령은 `ml-platform-engineering-labs` 저장소 최상위 폴더에서 실행한다. `ml-platform-book-env`로 이동하는 3장은 예외다. 새 터미널에서는 작업 위치, `$W`와 사용할 Python 환경을 다시 지정한다. 다른 터미널의 변수와 가상환경은 이어지지 않는다.

API나 UI를 실행하는 터미널은 켜 두고 다른 터미널에서 요청한다. 이 가이드의 서버는 `127.0.0.1`에만 노출한다. 실습을 마친 서버는 그 터미널에서 `Ctrl+C`로 종료한다.

### 서로 다른 환경을 한꺼번에 설치하지 않는다

책의 원본 경로와 독립 구현의 의존성은 다르다. 책 4~5장의 서버용 MLflow 3.0.0과 이 가이드의 MLflow 2.16.2를 같은 환경에 섞지 않는다.

| 환경 경로 | 사용하는 구간 | 설치할 extra |
| --- | --- | --- |
| `.ml-labs\book-env-base` | 기본 데이터, 추천, API와 로컬 RAG | `dev` |
| `.ml-labs\book-env-tools` | Feast, KFP와 Evidently | `dev`, `feast`, `pipeline`, `monitor` |
| `.ml-labs\book-env-bento` | BentoML | `dev`, `bento` |
| `.ml-labs\book-env-vision` | 실제 YOLO 학습 | `dev`, `vision` |
| 별도 생성, 평가 환경 | 외부 LLM, DeepEval, Langfuse | 선택한 연결에 필요한 extra만 |

각 환경은 같은 소스와 `uv.lock`을 사용한다. `uv sync --all-extras`는 지원하지 않는다. 라이브러리 충돌 때문에 모든 도구를 한 가상환경에 넣는 방식은 사용하지 않는다.

## 1장. 환경과 실행 출처를 준비한다 {#chapter-01}

먼저 설치한 Python과 내려받은 코드가 무엇인지 고정한다. 아직 GPU나 클라우드 계정은 필요하지 않다.

```powershell
git clone https://github.com/johklo/ml-platform-engineering-labs.git
Set-Location ml-platform-engineering-labs
git checkout --detach ff23b38f88d88268216e2985ff5b6ed0c3defb8c
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv sync --locked --python 3.12 --extra dev
uv run --locked --extra dev python --version
uv run --locked --extra dev ml-labs --help
```

위 커밋은 이 안내의 명령을 대조한 코드다. 이후 코드를 수정하면 별도 브랜치를 만들고 변경 커밋을 기록한다. 실행 코드를 수정한 상태에서 원래 커밋의 결과라고 표시하지 않는다.

외부 MLflow 서버가 설정돼 있는지도 확인한다.

```powershell
Get-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue
```

이 로컬 과정에 필요 없는 값이라면 현재 터미널에서만 제거한다.

```powershell
Remove-Item Env:MLFLOW_TRACKING_URI -ErrorAction SilentlyContinue
```

**완료 기준:** Python과 CLI가 실행되고, Git 커밋과 작업 위치를 확인할 수 있다. 명령을 찾지 못하면 PATH와 `uv` 설치를 먼저 해결한다. Python 3.13 이상으로 넘어가 의존성 오류를 우회하지 않는다.

## 2장. 생애주기를 작은 실행으로 확인한다 {#chapter-02}

도구를 모두 설치하기 전에 데이터 준비, 후보 생성, 평가와 등록이 이어지는지 확인한다.

```powershell
uv run --locked --extra dev ml-labs smoke --work "$W\smoke"
Get-Content "$W\smoke\runs\movies\candidate.json"
Get-Content "$W\smoke\reports\movies.json"
Get-ChildItem "$W\smoke"
```

`candidate.json`은 모델 자체가 아니라 원천 run, 모델 URI와 데이터 지문을 연결한 명세다. 평가 보고서는 그 후보에 묶인다. 등록된 모델 URI는 구체 버전을 포함해야 한다.

이 실행의 카드는 색상 규칙 기준선이고 문서 응답은 검색 문장 인용이다. 여기서 세 프로젝트가 성공해도 YOLO 학습이나 LLM 생성이 완료된 것은 아니다.

**완료 기준:** 세 프로젝트의 후보와 보고서, 로컬 Tracking DB가 생긴다. 기존 데이터가 있는 폴더를 덮어쓰라는 오류가 나오면 지우지 말고 `book-02`처럼 새 `$W`로 시작한다.

## 3장. 로컬 실행과 클러스터 실행을 구분한다 {#chapter-03}

컨테이너와 Kubernetes는 Python 설치에 포함되지 않는다. 먼저 엔진과 클라이언트를 확인한다.

```powershell
docker version
kubectl version --client
kind version
```

`docker version`에는 Client뿐 아니라 Server 정보도 나와야 한다. Windows에서 `dockerDesktopLinuxEngine` 연결 오류가 나오면 Docker Desktop의 Linux 엔진을 시작하고 다시 확인한다. 엔진이 준비되지 않았다면 이미지 빌드나 KFP 실행 단계로 넘어가지 않는다.

책 4~5장을 실제 클러스터에서 실행할 환경은 별도 저장소를 사용한다. 상위 폴더에 내려받고 그 저장소 안에서 실행한다.

```powershell
Push-Location ..
git clone https://github.com/johklo/ml-platform-book-env.git
Set-Location ml-platform-book-env
python bookenv.py check
python bookenv.py up
python bookenv.py status
Pop-Location
```

위 저장소는 kind의 `book-env`에 KFP standalone, S3 호환 저장소, PostgreSQL, Redis와 MLflow를 준비한다. 전체 Kubeflow와 Notebooks를 설치하는 명령은 아니다. 설치 요구 자원과 버전은 [책 4~5장 환경 설명](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/#book-lab-sop)에서 확인한다.

다른 터미널을 `ml-platform-book-env` 최상위 폴더에서 열고 접속을 유지한다.

```powershell
python bookenv.py forward
```

KFP는 `http://localhost:8080`, 책 실습의 MLflow는 `http://localhost:5000`, 저장소 화면은 `http://localhost:8888/buckets/`다. 로컬 MLflow UI와 5000번 포트를 동시에 사용하지 않는다.

**완료 기준:** 클러스터 Pod와 KFP 화면이 준비된다. 단순히 kind 클러스터가 만들어진 상태와 플랫폼 Pod가 요청 가능한 상태는 다르다. 이 판을 작성한 환경에서는 Docker 엔진이 중단돼 있어 이 클러스터 경로를 새로 실행하지 못했다. 이후의 로컬 컴포넌트 검사를 클러스터 실행으로 대체 표시하지 않는다.

## 4장. 실험, 평가와 등록을 연결한다 {#chapter-04}

다시 `ml-platform-engineering-labs` 폴더의 기본 환경으로 돌아온다. 이 경로는 책의 소득 분류를 복제하는 것이 아니라 작은 추천 데이터로 같은 기록과 등록 책임을 익히는 독립 구현이다. 소득 분류 원본은 [4~5장 실행 참조](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/#book-lab-sop)에 별도로 남겼다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs movies prepare --output "$W\data\movies"
uv run --locked --extra dev ml-labs movies train --data "$W\data\movies" --output "$W\runs\movies" --work "$W\tracking" --rank 4
uv run --locked --extra dev ml-labs movies evaluate --candidate "$W\runs\movies\candidate.json" --data "$W\data\movies" --report "$W\reports\movies.json"
uv run --locked --extra dev ml-labs register --candidate "$W\runs\movies\candidate.json" --report "$W\reports\movies.json" --name book-movie
Get-Content "$W\runs\movies\candidate.json"
```

각 명령이 성공했는지 확인하고 다음 명령을 실행한다. 평가 실패에서 그대로 등록을 계속하지 않는다. 등록 뒤에는 `registered_uri`가 `models:/book-movie/숫자` 형태인지 확인한다.

화면에서 보고 싶다면 별도 터미널에서 같은 기본 환경을 선택하고 실행한다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
$db = (Resolve-Path "$W\tracking\tracking.db").Path.Replace('\', '/')
uv run --locked --extra dev mlflow ui --backend-store-uri "sqlite:///$db" --host 127.0.0.1 --port 5001
```

`http://localhost:5001`에서 `ml-platform-labs`의 run을 찾는다. SQLite는 메타데이터이고 모델 파일은 별도 아티팩트다. DB만 복사하면 모델이 함께 복사되는 것은 아니다.

### 평가를 일부러 실패시킨다

```powershell
uv run --locked --extra dev ml-labs movies evaluate --candidate "$W\runs\movies\candidate.json" --data "$W\data\movies" --report "$W\reports\movies-rejected.json" --max-rmse 0.01
$LASTEXITCODE
uv run --locked --extra dev ml-labs register --candidate "$W\runs\movies\candidate.json" --report "$W\reports\movies-rejected.json" --name must-not-register
```

평가와 등록 모두 실패하는 것이 기대 동작이다. 거절 보고서를 정상 보고서로 덮어쓰지 않는다.

### 실제 Feast로 시점과 온라인 적재를 확인한다

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-tools"
uv sync --locked --python 3.12 --extra dev --extra feast --extra pipeline --extra monitor
uv run --locked --extra feast ml-labs tools feast init --data "$W\data\movies" --output "$W\feast"
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action apply
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action historical --user-id u007
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action online --user-id u007
```

마지막 온라인 조회는 아직 값이 없어서 실패해야 한다. 정의 등록과 값 적재는 다른 작업이다.

```powershell
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action materialize
uv run --locked --extra feast ml-labs tools feast run --repo "$W\feast" --action online --user-id u007
```

이제 학습 평점에서 계산한 온라인 피처를 읽는다. 이 예제의 Online store는 실제 Feast의 SQLite 구현이며 책의 Redis 설치를 대체 검증한 것은 아니다.

**완료 기준:** 거절 후보는 등록되지 않고, 과거 조회는 당시 값만 사용하며, 온라인 조회는 적재 전 실패하고 적재 후 성공한다.

## 5장. 컴포넌트를 연결하고 실행 경계를 확인한다 {#chapter-05}

KFP SDK로 준비, 학습과 평가를 컴파일한다.

```powershell
$revision = git rev-parse HEAD
uv run --locked --extra pipeline ml-labs tools kfp compile --source-revision $revision --output "$W\kfp\movie-pipeline.yaml"
Get-Content "$W\kfp\movie-pipeline.yaml" -TotalCount 60
uv run --locked --extra dev --extra pipeline pytest -q tests\test_optional_integrations.py -k "native_kfp or kfp_component_bodies"
```

검사는 실제 KFP 컴포넌트 본문으로 데이터, MLflow 모델 bundle과 평가 파일을 전달한다. Kubernetes Pod를 실행하는 검사는 아니다. 기본 컴파일의 이미지는 자리표시자이므로 그대로 제출하지 않는다.

3장의 Docker와 KFP가 준비됐을 때만 실제 이미지를 만든다.

```powershell
$revision = git rev-parse HEAD
docker build --platform linux/amd64 --build-arg SOURCE_REVISION=$revision -t book-labs:ff23b38 .
kind load docker-image book-labs:ff23b38 --name book-env
uv run --locked --extra pipeline ml-labs tools kfp compile --source-revision $revision --image book-labs:ff23b38 --output "$W\kfp\movie-pipeline.yaml"
uv run --locked --extra pipeline python -c "import sys,kfp; run=kfp.Client(host='http://127.0.0.1:8080').create_run_from_pipeline_package(sys.argv[1],arguments={'rank':4},experiment_name='book-guide',enable_caching=False); print(run.run_id)" "$W\kfp\movie-pipeline.yaml"
```

이 주소는 3장의 로컬 KFP standalone 전용이다. 인증이 있는 다른 클러스터에는 그대로 사용하지 않는다. 공유 클러스터에서는 이미지 접근 권한과 아티팩트 저장소도 따로 맞춘다.

**완료 기준:** 실제 클러스터 경로에서는 KFP run ID와 준비, 학습, 평가 작업의 로그 및 아티팩트를 확인한다. 이미지 빌드 실패, `ErrImagePull`과 저장소 연결 오류를 각각 나눈다. 컴파일 성공만으로 이 장을 클러스터 실행 완료로 표시하지 않는다.

## 6장. 등록 모델을 HTTP와 BentoML로 사용한다 {#chapter-06}

먼저 기본 API를 확인한다. 새 터미널에서 실행하고 켜 둔다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs serve --movies "$W\runs\movies\candidate.json" --host 127.0.0.1 --port 8000
```

다른 터미널에서 기존 사용자와 처음 보는 사용자를 비교한다.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
$body = @{ user_id = "u000" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/recommend -Method Post -ContentType application/json -Body $body
$body = @{ user_id = "new-user" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/recommend -Method Post -ContentType application/json -Body $body
```

기존 사용자는 `personalized`, 새 사용자는 `cold_start_popularity`다. 이후 그 서버를 종료한다.

BentoML은 전용 환경에서 같은 등록 모델을 가져온다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-bento"
uv sync --locked --python 3.12 --extra dev --extra bento
uv run --locked --extra bento ml-labs tools bento build --candidate "$W\runs\movies\candidate.json" --output "$W\bento"
uv run --locked --extra bento bentoml build "$W\bento"
uv run --locked --extra bento bentoml serve service:PlatformLabService --working-dir "$W\bento" --host 127.0.0.1 --port 3000
```

`tools bento build`는 가져오기와 서비스 파일 생성, `bentoml build`는 Bento 패키지 생성이다. 컨테이너 생성과 Kubernetes 배포는 여기에 포함되지 않는다. 이 경로는 BentoML 1.3.10의 구현이며 책의 1.1.10 Service, Runner 선언을 섞지 않는다.

클라이언트 요청 구조도 기본 API와 다르다.

```powershell
$body = @{ request = @{ user_id = "u000" } } | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:3000/predict -Method Post -ContentType application/json -Body $body
```

**완료 기준:** 같은 모델의 구체 버전을 서비스에서 읽고 실제 요청에 응답한다. 모델 등록 성공, Bento 생성, 서버 시작과 요청 성공을 각각 확인한다. 드리프트 보고서는 11장에서 같은 실행의 데이터에 연결한다.

## 7장. 다음 학습이 사용할 데이터를 준비한다 {#chapter-07}

기본 환경으로 돌아온다. 앞에서 만든 추천 데이터는 다시 덮어쓰지 않는다. 여기서는 이미지 준비와 실제 MovieLens 교체 경로를 확인한다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs cards prepare --output "$W\data\cards" --train 80 --validation 20 --test 20
Get-ChildItem "$W\data\cards\images\train" | Select-Object -First 3
Get-ChildItem "$W\data\cards\labels\train" | Select-Object -First 3
Get-Content "$W\data\cards\manifest.json"
```

이미지와 같은 stem의 라벨을 연결한다. YOLO 라벨은 클래스, 정규화 중심 좌표와 너비, 높이다. 빈 라벨은 카드가 없는 음성 표본일 수 있다. 이 데이터에는 실제 신분증이나 개인정보가 없다.

실제 평점으로 바꾸려면 [GroupLens의 이용 조건](https://grouplens.org/datasets/movielens/latest/)을 확인하고 `ml-latest-small.zip`을 직접 내려받아 저장소 최상위 폴더에 놓는다.

```powershell
uv run --locked --extra dev ml-labs movies import-movielens --archive .\ml-latest-small.zip --output "$W\data\movielens"
Get-Content "$W\data\movielens\manifest.json"
```

이 가져오기는 원천 지문, 평점 변환과 사용자별 시간 분할을 기록한다. 책의 25M 전체 자료를 현재 조밀 SVD에 바로 넣는 명령은 아니다. 대규모 희소 학습과 모든 원본 데이터 준비 구현은 별도 경로로 남아 있다.

**완료 기준:** 데이터 내용뿐 아니라 지문, 분할과 변환의 의미를 확인한다. `random_state`만 고정했다고 미래 정보나 같은 영상의 인접 프레임 누수가 해결되지는 않는다.

## 8장. 기준선과 실제 탐지 학습을 구분한다 {#chapter-08}

먼저 비교할 색상 기준선을 실행한다.

```powershell
uv run --locked --extra dev ml-labs cards train --data "$W\data\cards" --output "$W\runs\cards" --work "$W\tracking"
uv run --locked --extra dev ml-labs cards evaluate --candidate "$W\runs\cards\candidate.json" --data "$W\data\cards" --report "$W\reports\cards.json"
uv run --locked --extra dev ml-labs register --candidate "$W\runs\cards\candidate.json" --report "$W\reports\cards.json" --name book-card-baseline
```

그다음 전용 환경에서 실제 YOLO를 학습한다.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-vision"
uv sync --locked --python 3.12 --extra dev --extra vision
New-Item -ItemType Directory -Path "$W\yolo-config" -Force | Out-Null
$env:YOLO_CONFIG_DIR = (Resolve-Path "$W\yolo-config").Path
uv run --locked --extra vision yolo settings mlflow=False sync=False
uv run --locked --extra vision ml-labs cards train --data "$W\data\cards" --output "$W\runs\cards-yolo" --work "$W\tracking" --backend yolov8 --epochs 10
uv run --locked --extra vision ml-labs cards evaluate --candidate "$W\runs\cards-yolo\candidate.json" --data "$W\data\cards" --report "$W\reports\cards-yolo.json" --min-iou 0.5
```

Ultralytics의 설정은 이 실습 폴더로 격리한다. 자동 MLflow 콜백은 끄고 실습 코드가 학습 후 같은 Tracking DB에 모델을 기록하도록 한다. 자동 콜백을 켜 두면 별도 `runs\mlflow`에 기록하거나 Windows 경로를 URI로 잘못 해석해 학습 전에 실패할 수 있다. 이 설정은 다른 프로젝트의 Ultralytics 설정을 바꾸지 않는다. 새 터미널에서 학습을 이어 할 때도 `YOLO_CONFIG_DIR`을 다시 지정한다.

초기 가중치를 다운로드할 수 있고 CPU 학습에는 시간이 걸린다. 검증으로 선택한 `best.pt`와 MLflow 모델 아티팩트를 확인한다. 평가를 통과한 경우에만 해당 후보를 등록한다. 기준선보다 낮으면 데이터, 학습 로그와 오류 사례를 먼저 읽는다.

```powershell
uv run --locked --extra vision ml-labs register --candidate "$W\runs\cards-yolo\candidate.json" --report "$W\reports\cards-yolo.json" --name book-card-yolo
```

작은 실제 학습과 재로딩을 점검하는 명령도 있다.

```powershell
$env:ML_LABS_RUN_VISION = "1"
uv run --locked --extra dev --extra vision pytest -q tests\test_vision.py
Remove-Item Env:ML_LABS_RUN_VISION
```

검사를 마치고 다른 프로젝트로 이동할 때는 현재 터미널의 `YOLO_CONFIG_DIR`도 제거한다.

```powershell
Remove-Item Env:YOLO_CONFIG_DIR -ErrorAction SilentlyContinue
```

**완료 기준:** 규칙 기준선과 학습 가중치를 구분하고, 실제 YOLO 모델을 저장한 뒤 다시 읽어 추론한다. 1 epoch 검사의 성공이나 합성 데이터 IoU를 실제 신분증 환경의 mAP 인증으로 해석하지 않는다.

## 9장. 추천 후보를 검증 데이터로 선택한다 {#chapter-09}

4장의 테스트 결과를 모델 선택에 다시 사용하지 않는다. 새 실험 데이터에서 rank 2와 4를 비교한다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs movies prepare --output "$W\data\movies-ch09" --seed 43
uv run --locked --extra dev ml-labs movies train --data "$W\data\movies-ch09" --output "$W\runs\movies-rank2" --work "$W\tracking" --rank 2
uv run --locked --extra dev ml-labs movies train --data "$W\data\movies-ch09" --output "$W\runs\movies-rank4" --work "$W\tracking" --rank 4
```

검증 NDCG가 높은 후보를 우선하고 같으면 검증 RMSE가 낮은 후보를 선택한다.

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
$ranked
$MovieCandidate = $ranked[0].Path
uv run --locked --extra dev ml-labs movies evaluate --candidate $MovieCandidate --data "$W\data\movies-ch09" --report "$W\reports\movie-selected.json"
uv run --locked --extra dev ml-labs register --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --name book-movie-selected
$MovieCandidate | Set-Content "$W\selected-movie-path.txt" -Encoding utf8
```

평가가 실패하면 여기서 멈춘다. 등록되지 않은 후보로 출시를 계속하지 않는다. 후보 선정 전에 테스트를 여러 번 비교하지 않는다.

이 모델은 SVD 추천 구현이다. RMSE는 평점 오차이고 Recall, NDCG는 추천 순위의 다른 측면이다. 관련 영화가 있는 사용자 수와 인기 기준선 결과도 함께 읽는다. 책의 모든 추천 알고리즘과 대규모 학습을 재현한 것은 아니다.

**완료 기준:** 선택 이유가 테스트 점수 아닌 검증 지표에 있고, 선택 후보의 최종 평가와 구체 등록 버전이 남는다.

## 10장. 출시, 요청과 배치 재처리를 연결한다 {#chapter-10}

선택 후보를 출시 기록으로 묶는다.

```powershell
$MovieCandidate = (Get-Content "$W\selected-movie-path.txt" -Raw).Trim()
uv run --locked --extra dev ml-labs release activate --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --store "$W\movie-releases"
uv run --locked --extra dev ml-labs release show --store "$W\movie-releases"
```

별도 기본 환경 터미널에서 서버를 실행한다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs serve --movie-release "$W\movie-releases" --host 127.0.0.1 --port 8000
```

6장과 같은 요청을 보내 `release_id`, 고정 모델 URI와 응답을 확인한다. 이 영화 서버는 시작할 때 모델을 고정한다. 포인터 변경 뒤 실행 중 모델이 자동으로 바뀌는 구현은 아니다.

배치에서는 사용자 파일과 업무 키를 함께 넘긴다.

```powershell
@("user_id", "u000", "new-user") | Set-Content "$W\batch-users.csv" -Encoding utf8
uv run --locked --extra dev ml-labs batch --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --users "$W\batch-users.csv" --output "$W\batch-results" --job-key book-day-01 --fail-before-commit
```

완료 결과를 게시하기 전에 일부러 실패한다. 실패 옵션만 빼고 같은 작업을 두 번 실행한다.

```powershell
uv run --locked --extra dev ml-labs batch --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --users "$W\batch-users.csv" --output "$W\batch-results" --job-key book-day-01
uv run --locked --extra dev ml-labs batch --candidate $MovieCandidate --report "$W\reports\movie-selected.json" --users "$W\batch-users.csv" --output "$W\batch-results" --job-key book-day-01
```

두 번째 성공 실행에는 `reused: true`가 나와야 한다. 같은 업무 키에 다른 사용자나 모델을 넘기면 거절한다. 이는 단일 호스트 파일시스템 실험이며 분산 저장소 transaction이나 KServe 무중단 전환을 구현한 것은 아니다.

**완료 기준:** 모델 입력에서 ID를 제외해도 결과에는 누구의 예측인지 남고, 실패 뒤 재처리해도 동일 업무 결과가 중복되지 않는다. 서버는 11장의 `/metrics` 확인까지 유지한 뒤 종료한다.

### 탐지 모델의 저장과 서빙도 연결한다

8장에서 실제 YOLO 후보를 평가하고 등록한 경우 별도 터미널에서 전용 환경으로 실행한다. 추천 서버와 포트를 나눈다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-vision"
uv run --locked --extra vision ml-labs serve --cards "$W\runs\cards-yolo\candidate.json" --host 127.0.0.1 --port 8002
```

클라이언트 터미널에서는 테스트 이미지 하나를 요청한다.

```powershell
$image = Get-ChildItem "$W\data\cards\images\test" -Filter *.png | Select-Object -First 1
$body = @{image_path = $image.FullName} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8002/predict/cards -Method Post -ContentType application/json -Body $body
```

응답의 `backend`가 `yolov8`인지 확인한다. `detected`가 참일 때 좌표가 있고 거짓이면 `box_xyxy`는 비어 있다. 이 엔드포인트는 같은 컴퓨터의 파일 경로를 읽는 로컬 실습용이며 이미지 업로드 API가 아니다. 다른 호스트나 공개 서비스에 경로 입력을 그대로 노출하지 않는다. 확인 뒤 탐지 서버만 종료한다.

## 11장. 서비스 상태와 데이터 변화를 따로 관측한다 {#chapter-11}

10장의 서버가 실행 중일 때 `/metrics`를 확인한다.

```powershell
(Invoke-WebRequest http://127.0.0.1:8000/metrics).Content
```

요청 후 `ml_labs_inference_requests_total`과 지연 지표가 바뀌는지 본다. 이것은 계측이며 Prometheus, Grafana와 Alertmanager 설치 성공은 아니다.

원본 데이터는 바꾸지 않고 분포 비교용 파일을 따로 만든다.

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-tools"
uv run --locked --extra monitor python -c "import sys,pandas as pd; d=pd.read_csv(sys.argv[1]); d[['rating']].to_csv(sys.argv[2],index=False); d['rating']=1.0; d[['rating']].to_csv(sys.argv[3],index=False)" "$W\data\movies\ratings.csv" "$W\reference.csv" "$W\current.csv"
uv run --locked --extra monitor ml-labs tools drift --reference "$W\reference.csv" --current "$W\current.csv" --output "$W\reports\drift.json" --backend evidently
Get-Content "$W\reports\drift.json" -TotalCount 30
Start-Process "$W\reports\drift.html"
```

보고서는 실제 Evidently가 계산한 결과다. 변화한 입력 분포와 모델 정확도는 다른 증거이므로 자동 재학습으로 바로 연결하지 않는다. 정답, 수집 오류와 업무 영향을 추가로 확인한다.

실제 피처 공급, 요청 분기, 저장 실패와 출시 복구까지 연결하려면 별도의 새 폴더로 통합 실험을 실행한다.

```powershell
uv run --locked --extra dev --extra feast --extra monitor ml-labs exercise --work "$W\integrated"
$evidence = Get-Content "$W\integrated\evidence.json" -Raw | ConvertFrom-Json
$evidence.feature_failure_http
$evidence.feature_recovery.status
$evidence.batch.retried.reused
$evidence.releases
```

공급 전 503, 공급 후 개인화 응답, 재처리 재사용과 최초 release 복구를 확인한다. [통합 실험의 개별 단계](../ml-platform-labs-09-integrated-operations/)에는 직접 실패를 주입하는 절차가 있다.

**완료 기준:** 정상 HTTP, 입력 변화와 실제 품질을 구분하고, 보고서와 복구 결과가 남는다. Eigen-CAM, EMF와 Deepchecks 등 책의 설명가능성, 검사 도구 전체는 이 실행에 포함되지 않는다.

## 12장. 같은 문서와 설정으로 검색과 응답을 만든다 {#chapter-12}

기본 환경에서 공개 합성 문서로 시작한다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs rag release init-demo --output "$W\rag\inputs"
Get-Content "$W\rag\inputs\config.json"
Get-Content "$W\rag\inputs\evaluation.json"
uv run --locked --extra dev ml-labs rag release create --corpus "$W\rag\inputs\documents.jsonl" --config "$W\rag\inputs\config.json" --prompt "$W\rag\inputs\prompt.json" --evaluation "$W\rag\inputs\evaluation.json" --output "$W\rag\v1"
uv run --locked --extra dev ml-labs rag release evaluate --candidate "$W\rag\v1\candidate.json" --report "$W\rag\v1-report.json"
uv run --locked --extra dev ml-labs rag release activate --store "$W\rag\store" --candidate "$W\rag\v1\candidate.json" --report "$W\rag\v1-report.json"
uv run --locked --extra dev ml-labs rag release query --store "$W\rag\store" --query "model registry champion promotion"
uv run --locked --extra dev ml-labs rag release query --store "$W\rag\store" --query "quasar teleportation warranty"
```

첫 질문에는 근거 문서 인용이, 두 번째에는 `no_grounding`과 빈 인용이 나와야 한다. 문서, 검색 설정, 프롬프트와 평가 집합은 후보의 해시로 고정된다.

기본 provider는 `extractive_offline`이다. TF-IDF로 찾은 문장을 인용하며 LLM이 새 답변을 생성하지 않는다. 이를 책의 Gemini, FAISS, LangChain과 Chainlit 구현 완료로 표시하지 않는다.

### 실제 생성 모델은 별도 연결과 검증이 필요하다

기존 Azure OpenAI를 사용하는 독립 생성 경로는 [RAG 출시 가이드의 생성 연결](../ml-platform-labs-10-rag-release/)에 있다. 필요한 것은 기존 endpoint, 배포 이름, 인증과 예산이다. 그 경로도 책의 Gemini 실행과 같은 도구는 아니다.

생성 모드에서는 고정한 검색 결과와 프롬프트가 실제 요청에 사용되는지, 인용이 검색된 문서에 포함되는지 확인한다. 형식 검사 통과가 답변의 모든 주장이 사실이라는 증거는 아니다. 키가 없는 상태에서 가짜 생성 결과를 넣어 통과시키지 않는다.

**완료 기준:** 로컬 검색과 거절 경로가 평가한 후보와 일치한다. 실제 생성 완료를 표시하려면 선택한 모델의 외부 요청과 응답, 평가 근거를 별도로 남겨야 한다.

## 13장. 변경을 평가하고 출시를 거절하거나 되돌린다 {#chapter-13}

원본 v1은 그대로 두고 검색 임계치를 잘못 높인 후보를 만든다.

```powershell
$badConfig = Get-Content "$W\rag\inputs\config.json" -Raw | ConvertFrom-Json
$badConfig.min_score = 1.0
$badConfig | ConvertTo-Json -Depth 10 | Set-Content "$W\rag\bad-config.json" -Encoding utf8
uv run --locked --extra dev ml-labs rag release create --corpus "$W\rag\inputs\documents.jsonl" --config "$W\rag\bad-config.json" --prompt "$W\rag\inputs\prompt.json" --evaluation "$W\rag\inputs\evaluation.json" --output "$W\rag\bad"
uv run --locked --extra dev ml-labs rag release evaluate --candidate "$W\rag\bad\candidate.json" --baseline "$W\rag\v1\candidate.json" --min-pass-rate 0.3 --max-regression 0 --report "$W\rag\bad-report.json"
uv run --locked --extra dev ml-labs rag release activate --store "$W\rag\store" --candidate "$W\rag\bad\candidate.json" --report "$W\rag\bad-report.json"
```

평가와 활성화는 실패해야 한다. 전체 통과율 조건을 느슨하게 해도 기존에 답하던 사례를 잃으면 회귀 게이트로 차단한다. 실패 뒤 active release가 v1인지 질의로 확인한다.

이번에는 정상 변경을 평가한 뒤 복구한다.

```powershell
$v2Config = Get-Content "$W\rag\inputs\config.json" -Raw | ConvertFrom-Json
$v2Config.top_k = 3
$v2Config | ConvertTo-Json -Depth 10 | Set-Content "$W\rag\v2-config.json" -Encoding utf8
uv run --locked --extra dev ml-labs rag release create --corpus "$W\rag\inputs\documents.jsonl" --config "$W\rag\v2-config.json" --prompt "$W\rag\inputs\prompt.json" --evaluation "$W\rag\inputs\evaluation.json" --output "$W\rag\v2"
uv run --locked --extra dev ml-labs rag release evaluate --candidate "$W\rag\v2\candidate.json" --baseline "$W\rag\v1\candidate.json" --report "$W\rag\v2-report.json"
uv run --locked --extra dev ml-labs rag release activate --store "$W\rag\store" --candidate "$W\rag\v2\candidate.json" --report "$W\rag\v2-report.json"
uv run --locked --extra dev ml-labs rag release rollback --store "$W\rag\store"
uv run --locked --extra dev ml-labs rag release query --store "$W\rag\store" --query "model registry champion promotion"
```

복구 후 응답의 `release_id`가 v1로 돌아왔는지 확인한다. 후보 평균 점수가 좋다는 주장과 실제 서버가 그 후보로 응답한다는 증거는 다르다.

### HTTP 응답에서도 활성 버전을 확인한다

별도 기본 환경 터미널에서 같은 출시 저장소를 연결한다.

```powershell
$W = ".ml-labs\book-01"
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev ml-labs serve --rag-release "$W\rag\store" --host 127.0.0.1 --port 8003
```

클라이언트 터미널에서 실제 응답을 확인한다.

```powershell
$body = @{query = "model registry champion promotion"} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8003/rag/query -Method Post -ContentType application/json -Body $body
```

위의 v2 활성화 명령과 rollback 명령을 다시 실행하고, 각각 HTTP 질의의 `release_id`를 비교한다. 이 RAG 서버는 요청마다 활성 스냅샷을 읽으므로 서버 재시작 없이 변경과 복구가 반영된다. 10장의 시작 시 고정하는 추천 서버와 다른 계약이다. 확인 뒤 서버를 종료한다.

### 실제 RAG 런타임을 Promptfoo로 검사한다

Node.js가 준비됐을 때 실행한다. 별도 프롬프트 예제를 평가하지 않고 위 후보를 직접 호출한다.

```powershell
uv run --locked --extra dev ml-labs tools promptfoo release-config --candidate "$W\rag\v1\candidate.json" --output "$W\rag\promptfoo.yaml"
$env:PROMPTFOO_PYTHON = (Resolve-Path "$env:UV_PROJECT_ENVIRONMENT\Scripts\python.exe").Path
$env:PROMPTFOO_DISABLE_TELEMETRY = "1"
npm exec --yes --package=promptfoo@0.125.0 -- promptfoo eval --config "$W\rag\promptfoo.yaml" --no-cache --output "$W\rag\promptfoo-results.json"
```

초기 패키지 다운로드에는 네트워크가 필요하다. 로컬 인용 후보에는 유료 생성 API가 필요하지 않다. 이 결과는 프로젝트의 출시용 평가 보고서를 대신하지 않는다.

DeepEval의 의미 평가와 Langfuse 외부 추적은 [별도 연결 절차](../ml-platform-labs-10-rag-release/)로 진행한다. 공개 합성 문서와 질문만 전송하며 실제 요청 성공을 확인하기 전에는 외부 연결 완료로 표시하지 않는다. 의미 캐시, 문서별 권한과 비용 강제 제한은 아직 이 로컬 실행판에 구현되지 않았다.

**완료 기준:** 회귀 후보는 차단되고, 통과 후보의 활성화와 이전 버전 복구가 실제 질의 결과에 반영된다. 이 단일 호스트 실험을 조직 승인, 다중 사용자 권한과 종합적인 LLM 안전성 평가로 해석하지 않는다.

## 구현과 검증 범위 {#verification-scope}

이 가이드는 [공개 코드의 고정 커밋](https://github.com/johklo/ml-platform-engineering-labs/tree/ff23b38f88d88268216e2985ff5b6ed0c3defb8c)을 기준으로 한다. 원문 명령의 순서를 그대로 복사한 것이 아니라 기존 독립 구현과 책의 실행 참조를 연결했다.

| 구간 | 이 판에서 실행으로 확인한 것 | 책 전체 실습 완료에 남은 것 |
| --- | --- | --- |
| 1~2장 | 데이터 계약, MLflow 기록, 평가와 등록, 실패 검사 | 조직별 책임과 운영 승인 체계 |
| 3~5장 | 실제 Feast 조회와 적재, KFP 컴파일과 컴포넌트 본문 실행 | 현재 Docker 엔진을 복구한 뒤 이미지와 KFP 클러스터 재실행, GitLab CI와 Argo CD 전체 경로 |
| 6장 | 로컬 HTTP 요청과 모델 버전, 실제 BentoML 모델 가져오기, 패키징과 HTTP 응답 | Yatai 또는 선택 배포 관리자의 실제 클러스터 출시 |
| 7~9장 | 합성 준비, 실제 CPU YOLO 10 epoch 학습과 검증 후 테스트, MLflow 재로딩, 추천 후보와 평가 | 원본 데이터 전체, 책의 학습 알고리즘과 대규모 처리, 표준 mAP 기반 정책 |
| 10~11장 | 등록 YOLO의 HTTP 추론, 추천 요청, 배치 실패와 멱등 재시도, 출시 복구, Evidently 보고서 | KServe, 운영 관측 스택, Deepchecks, Eigen-CAM과 EMF 전체 |
| 12~13장 | 동일 후보의 검색, 거절, 회귀 차단, HTTP에서 재시작 없는 활성화와 복구, 실제 후보를 호출하는 Promptfoo | Gemini, FAISS, LangChain, Chainlit 원본 경로, 실제 외부 생성 및 의미 평가, 권한과 캐시, 비용 제한 |

선택 테스트의 `skipped`는 검증 성공이 아니다. 위 합성 데이터의 10 epoch 학습과 IoU 게이트는 실행으로 확인했지만 다른 데이터나 실제 촬영 환경의 품질을 보증하지 않는다. 공개 합성 문서에서의 RAG 성공은 실제 업무 문서의 답변 품질을 인증하지 않는다.

책의 모든 실습을 완성하려면 이 표의 남은 경로를 구현하고, 해당 실행 환경에서 증거를 추가해야 한다. 특히 현재 중단된 Docker 엔진과 외부 서비스 인증, 비용 조건은 로컬 단위 검사로 대신할 수 없다.

## 다음 날 다시 시작하고 정리하기

기존 `$W`를 이어 쓸 때는 만들어진 데이터와 후보를 다시 덮어쓰지 않는다. 현재 단계의 입력 파일, 등록 버전과 보고서를 확인한 뒤 다음 명령부터 진행한다. 새 실험은 새 작업 경로를 사용한다.

```powershell
$W = ".ml-labs\book-01"
Get-ChildItem $W
git rev-parse HEAD
$env:UV_PROJECT_ENVIRONMENT = ".ml-labs\book-env-base"
uv run --locked --extra dev pytest -q
```

API와 UI는 각각의 터미널에서 종료한다. 포트포워딩 종료는 클러스터 삭제가 아니다. 실습 결과와 모델의 연결을 확인하기 전에 Tracking DB나 아티팩트만 따로 지우지 않는다. 공유 클러스터나 다른 사람의 실행은 정리 대상이 아니다.

원리와 책의 차이를 다시 보고 싶다면 [책 해설](/docs/tech/machine-learning-platform-engineering/00-overview/)로, 도구별 상세 실패 실험은 [통합 실습 목차](../)로 돌아간다.
