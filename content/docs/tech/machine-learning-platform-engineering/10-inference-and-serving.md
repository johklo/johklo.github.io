---
title: "10. 모델 추론과 서빙"
description: "8장의 신분증 탐지 모델과 9장의 추천 모델을 BentoML, MLflow, KServe로 실제 API로 띄우며 서비스, 패키지, 이미지, 배포의 경계와 출시 정보, 롤백 단위를 확인하기"
date: 2026-10-18T21:30:00+09:00
lastmod: 2026-11-08T15:00:00+09:00
weight: 100
draft: false
tags: ["book-club", "ml-platform-engineering", "bentoml", "mlflow", "kserve", "model-serving"]
---

9장까지 손에 쥔 것은 파일이었다. 8장은 `best.pt`를 남겼고, 9장은 MLflow에 `model.pth`와 `staging` 별칭을 남겼다. 파일만으로는 다른 프로그램이 모델을 쓸 수 없다. 누군가 요청을 받아 입력을 검사하고, 모델이 기대하는 모양으로 바꾸고, 약속한 형식으로 답을 돌려줘야 한다.

10장은 그 "누군가"를 만드는 장이다. 책은 BentoML로 탐지 모델을 API로 만들고(10.3~10.5), 이를 MLflow 레지스트리와 연결한다(10.6). MLflow만으로 서빙하는 길도 보여 주고(10.7), Kubernetes 쪽 대안으로 KServe를 소개한다(10.8).

책을 따라가다 보면 세 군데서 걸린다. 하나는 말이다. 모델 파일, 서비스 코드, Bento, 컨테이너 이미지, 배포가 모두 "모델을 배포했다"로 뭉뚱그려져 각각 무엇을 고정하는지 흐려진다. 또 하나는 버전이다. 책은 BentoML 1.1의 Service와 Runner로 설명하다가 추천 서비스 리스팅 10.1에서는 1.2 이후의 클래스 기반 API를 쓴다. 두 코드는 같은 버전으로 함께 돌지 않는다. 마지막은 KServe 절의 예시다. YOLO 모델에 scikit-learn 런타임을 지정하고 있어 그대로는 동작하지 않는다.

앞부분은 구성 요소들이 무엇을 주고받는지, 각 도구가 어디까지 책임지는지를 다룬다. 뒤의 [실습 순서](#book-ch10-sop)는 실제로 돌린 과정과 화면이다. 저자 코드가 지금 그대로 돌지 않는 곳과, 돌기는 하는데 틀린 답을 내는 곳도 함께 적었다. 직접 돌려 보니 곤란한 쪽은 뒤쪽이었다. 200 응답 뒤에 숨어 있어서다.

## 전체 그림 {#platform-map}

10장의 일은 등록된 모델을 요청 경로에 올리는 것이다. 아래 그림은 이번 실습에서 각 구성 요소가 어디서 실행됐고 번호 순서대로 무엇을 넘기는지 보여 준다. 레지스트리와 S3 저장소는 8~9장에서 만든 것이고, 오른쪽 끝의 관측은 11장이 이어받는다.

```mermaid
%%{init: {"flowchart": {"rankSpacing": 25, "nodeSpacing": 18, "padding": 6}}}%%
flowchart LR
    accTitle: 10장 실습에서 모델이 서비스와 배포로 이어지는 경로
    accDescr: MLflow 레지스트리에 있는 8장 탐지 모델과 9장 추천 모델을 개발자 PC가 내려받아 BentoML 1.1 탐지 서비스, BentoML 1.4 추천 서비스, MLflow pyfunc 서버로 실행하고 Bento로 묶는다. 같은 탐지 가중치를 S3 버킷에 복사하면 KServe 컨트롤러가 InferenceService 명세를 Deployment와 Service로 바꾸고, storage-initializer가 가중치를 Pod에 내려받아 예측 컨테이너가 요청을 처리한다. 요청 지표와 로그는 11장의 모니터링으로 이어진다.
    subgraph PC["개발자 PC"]
        CLIENT["클라이언트<br/>Swagger UI, curl"]
        YOLO["BentoML 1.1<br/>탐지 서비스"]
        REC["BentoML 1.4<br/>추천 서비스"]
        MLS["mlflow models serve<br/>pyfunc 서버"]
        BSTORE[("로컬 Bento 저장소")]
        KCTL["kubectl"]
    end
    subgraph KIND["kind 클러스터 book-env"]
        subgraph MLNS["mlflow 네임스페이스"]
            REG["MLflow 레지스트리<br/>ch08 탐지 v1, ch09 추천 v1과 v2"]
        end
        subgraph KFNS["kubeflow 네임스페이스"]
            S3[("S3 저장소<br/>mlflow-artifacts, ch09-datasets")]
            S3M[("S3 ch10-models 버킷")]
        end
        subgraph KSNS["kserve 네임스페이스"]
            KSC["KServe 컨트롤러<br/>Standard 모드"]
        end
        subgraph SVNS["ch10-serving 네임스페이스"]
            ISVC["InferenceService<br/>ch10-detector"]
            INIT["storage-initializer"]
            PRED["예측 컨테이너<br/>KServe V1 프로토콜"]
        end
    end
    NEXT["11장<br/>모니터링과 설명가능성"]

    REG -->|"① best.pt, 버전 정보"| YOLO
    CLIENT -->|"② 이미지, 박스 JSON"| YOLO
    YOLO -->|"③ Bento 태그"| BSTORE
    REG -->|"④ prod 별칭, model.pth"| REC
    S3 -->|"⑤ 영화 카탈로그"| REC
    REC -->|"⑥ Bento 태그"| BSTORE
    REG -->|"⑦ pyfunc 모델"| MLS
    YOLO -.->|"⑧ 가중치, model_info.json"| S3M
    KCTL -->|"⑨ InferenceService 명세"| KSC
    KSC -->|"⑩ Deployment, Service, HPA"| ISVC
    S3M -->|"⑪ /mnt/models"| INIT
    INIT --> PRED
    CLIENT -->|"⑫ V1 predict 요청"| PRED
    PRED -.->|"⑬ 지연, 오류, 모델 버전"| NEXT

    classDef thisch fill:#e8f1ff,stroke:#2f6fd6,stroke-width:2px;
    classDef prev fill:#f3f3f3,stroke:#999;
    classDef next fill:#fff6e5,stroke:#d08a00,stroke-dasharray:4 3;
    class CLIENT,YOLO,REC,MLS,BSTORE,KCTL,S3M,KSC,ISVC,INIT,PRED thisch;
    class REG,S3 prev;
    class NEXT next;
```

| 번호 | 누가 | 무엇을 넘기는가 | 어디에 남는가 | 실습 단계 |
| --- | --- | --- | --- | --- |
| ① | `fetch_detector.py` | `ch08-id-card-detector` v1의 `best.pt`, 버전과 run_id, sha256 | `ch10\yolo-fixed\` 폴더 | [B-1](#ch10-b-1) |
| ② | 클라이언트와 BentoML API 서버, Runner | 이미지와 박스 목록, 박스를 그린 이미지 | HTTP 응답, `x-model-version` 헤더 | [B-2](#ch10-b-2)~[B-4](#ch10-b-4) |
| ③ | `bentoml build` | 코드, 가중치, 의존성 목록을 묶은 Bento | 로컬 Bento 저장소 `yolo_v8:<태그>` | [C-1](#ch10-c-1), [C-2](#ch10-c-2) |
| ④ | 추천 서비스 초기화 | `ch10-recommender@prod`가 가리키는 버전의 모델 | 서비스 프로세스 메모리 | [D-2](#ch10-d-2), [D-3](#ch10-d-3) |
| ⑤ | 추천 서비스 초기화 | `movies.parquet.gzip`의 영화 ID 목록 | 서비스 프로세스 메모리 | [D-3](#ch10-d-3) |
| ⑥ | `bentoml build` | 추천 서비스 Bento와 잠근 의존성 목록 | 로컬 Bento 저장소 `recommender_service:<태그>` | [D-5](#ch10-d-5) |
| ⑦ | `mlflow models serve` | `ch10-recommender-pyfunc@prod` | 서버 프로세스 메모리 | [E-1](#ch10-e-1)~[E-3](#ch10-e-3) |
| ⑧ | 개발자 PC | B-1과 같은 가중치와 `model_info.json` | `ch10-models/detector/ch08-id-card-detector/1/` | [F-2](#ch10-f-2) |
| ⑨ | `kubectl apply` | 이미지, 저장 위치, 프로브, 자원을 적은 `InferenceService` | Kubernetes API의 커스텀 리소스 | [F-3](#ch10-f-3) |
| ⑩ | KServe 컨트롤러 | Deployment, Service, HPA | `ch10-serving` 네임스페이스 | [F-3](#ch10-f-3) |
| ⑪ | storage-initializer 초기화 컨테이너 | S3의 모델 파일 | Pod의 `/mnt/models` | [F-3](#ch10-f-3) |
| ⑫ | 클라이언트, 포트포워딩 | `instances[].image_b64` 요청과 예측 | HTTP 응답 | [F-4](#ch10-f-4), [F-6](#ch10-f-6) |
| ⑬ | 11장 | 요청 지표, 로그, 응답의 모델 버전 | 다음 장 | 이 장에서는 수집하지 않음 |

그림에서 따라갈 것은 모델 버전이 어디서 정해지는가다. ①과 ⑧은 빌드 시점에 버전을 고정한다. 파일을 Bento나 버킷 경로에 넣었으니 나중에 레지스트리가 바뀌어도 서비스가 쓰는 모델은 그대로다. ④와 ⑦은 실행 시점에 별칭을 해석한다. 같은 Bento로 다시 시작해도 별칭이 옮겨 갔으면 다른 모델이 뜬다. 두 경로의 출시 기록과 롤백 방식이 달라지는 이유다.

요청 하나가 서비스 안에서 흐르는 경로는 아래와 같다. B 구간의 BentoML 1.1 탐지 서비스를 기준으로 그렸다. API 서버와 Runner는 한 컴퓨터 안에서도 서로 다른 프로세스라, 그 사이를 오가는 이미지와 결과는 직렬화된다.

```mermaid
sequenceDiagram
    accTitle: BentoML 1.1 탐지 서비스의 요청 경로
    accDescr: 클라이언트가 이미지를 보내면 API 서버 프로세스가 MIME 형식과 크기를 검사해 잘못된 입력은 400으로 돌려보낸다. 통과한 이미지는 Runner 프로세스로 직렬화되어 넘어가고 Runner가 YOLO 모델로 박스를 계산해 돌려준다. API 서버는 응답에 모델 버전 헤더를 붙이고, 요청 수와 지연은 /metrics에 쌓인다.
    participant C as 클라이언트
    participant A as API 서버 프로세스
    participant R as Runner 프로세스
    participant M as /metrics
    C->>A: POST /invocation, image/jpeg
    A->>A: MIME 형식, 이미지 디코딩, 크기 검사
    alt 잘못된 입력
        A-->>C: 400과 오류 메시지
    else 정상 입력
        A->>R: 이미지 직렬화와 inference 호출
        R->>R: YOLO 추론, 박스 전체를 JSON으로
        R-->>A: 박스 목록, 없으면 빈 목록
        A-->>C: 200, x-model-version 헤더
    end
    A->>M: 요청 수, 응답 코드, 지연
    R->>M: Runner 요청 수와 지연
```

## 모델을 서비스로 만든다는 것 {#why-serving-is-hard}

책 10.1은 배포가 어려운 이유로 추론 패턴, 확장, 관측, 지속 학습, 데이터 의존성, 하드웨어, 버전 관리, 설명가능성, 자원, 보안을 든다. 목록은 길어도 뿌리는 하나다. 학습할 때는 모델과 데이터가 한 노트북 안에 있었고, 실패하면 사람이 다시 돌리면 됐다. 서빙에서는 모르는 사람이 모르는 입력을 모르는 시점에 보내고, 그 응답은 곧바로 다른 프로그램의 입력이 된다.

그래서 서빙 코드가 하는 일은 대부분 모델 계산의 주변이다. 입력이 약속한 모양인지 확인하고, 학습 때와 같은 방식으로 바꾸고, 약속한 형식으로 결과를 돌려주고, 어떤 버전이 응답했는지 남긴다.

이 일들을 한 덩어리로 보면 "모델을 배포했다"는 말이 무엇을 고정했는지 알 수 없다. 이 장의 산출물은 다섯 층으로 나뉘고, 층마다 버전을 가리키는 값이 다르다.

| 층 | 이번 실습의 예 | 무엇을 고정하는가 | 식별자 |
| --- | --- | --- | --- |
| 모델 아티팩트 | `best.pt`, MLflow의 `model.pth` | 가중치와 모델 구조 | 레지스트리 이름과 버전, run_id, 파일 sha256 |
| 서비스 | `service.py` | 입력 검증, 전처리, 응답 형식(API 계약), 모델 로딩 방식 | 코드 커밋 |
| 패키지 | Bento | 서비스 코드, 포함 파일, 파이썬 의존성 목록, 기반 이미지 지정 | Bento 태그 `yolo_v8:rxu4w6w3dcwsplaz` |
| 이미지 | `bentoml containerize` 결과 | 운영체제, 파이썬, 설치된 패키지의 실제 파일 | 이미지 digest |
| 배포 | `InferenceService`, Deployment | 복제 수, 자원, 프로브, 환경 변수, 저장 위치 | 리소스 명세와 generation |

핵심은 **한 층이 다른 층을 저절로 고정해 주지 않는다**는 점이다. 같은 Bento 태그라도 실행 시점에 MLflow 별칭을 읽으면 다른 모델이 뜬다. 같은 이미지라도 배포 명세의 환경 변수가 다르면 다른 버전을 서빙한다. 출시 기록은 다섯 층의 식별자를 한데 묶은 것이고, 롤백은 그 묶음 전체를 이전 값으로 되돌리는 일이다. 실제 값은 뒤의 [출시 정보와 롤백 단위](#release-and-rollback)에서 다시 본다.

책은 셀프서비스 배포의 장점을 강조하면서도, 그것이 비운영 환경 이야기라고 선을 긋는다. 데이터 과학자가 직접 띄워 검증하고, 운영 배포는 ML 엔지니어에게 넘긴다는 구분이다. 이번에 서빙하는 탐지 모델도 출시와는 거리가 있다. 8장의 수동 검토에서 흐린 사진, 작은 카드, 어두운 사진에 실패해 MLflow 버전 태그에 `release_decision: hold`가 남은 모델이다. 서빙할 수 있다는 것과 출시해도 된다는 것은 다른 판단이고, 이 장은 앞쪽만 확인한다.

## BentoML의 Service와 Runner {#bentoml-service-runner}

BentoML을 쓰는 이유는 이 주변 일을 매번 직접 짜지 않아도 되기 때문이다. 웹 서버, 입력 형식 변환, Swagger 문서, 상태 확인 경로, Prometheus 지표를 기본으로 주고, 의존성 목록을 묶은 패키지와 컨테이너 이미지도 만들어 준다. 모델 개발자는 "이 입력을 받아 이 모델을 부르고 이 형식으로 돌려준다"만 쓰면 된다.

책이 쓰는 BentoML 1.1은 **Service**와 **Runner** 두 층으로 되어 있다. Service는 HTTP 요청을 받는 API 서버 쪽이다. 입력을 파싱해 검증하고 응답을 변환한다. Runner는 모델을 감싼 계산 단위다. 자기 프로세스에 모델을 올려 두고 API 서버의 호출을 받아 추론한다.

[B-2](#ch10-b-2)에서 저자 코드를 그대로 띄우자 논리 CPU 16개짜리 PC에 API 서버 프로세스 16개와 Runner 프로세스 1개가 떴다. API 서버 수의 기본값이 CPU 수라서다. 책의 그림 10.3이 말하는 "여러 API 서버와 Runner"는 실제로 이런 모습이었다.

둘을 나누는 이유는 병목이 다르기 때문이다. 요청을 받고 이미지를 디코딩하는 일은 가볍고 동시에 많이 일어난다. 모델 계산은 무겁고 CPU나 GPU를 독점한다. 나눠 두면 API 서버는 늘리고 Runner는 가속기 수만큼만 두는 식으로 따로 조정할 수 있다.

대가는 직렬화다. 둘 사이의 값은 프로세스 경계를 넘어야 한다. `/render`의 결과를 메모리에서 그린 PIL 이미지로 돌려주자 Runner가 응답을 직렬화하다 `ValueError: unknown file extension`으로 실패했다. 메모리에서 만든 이미지에는 파일 형식 정보가 없어서다. 이 오류를 보고 나서야 저자 코드가 결과 이미지를 디스크에 저장했다가 다시 여는 이유가 보였다. 사실상 형식 정보를 얻기 위한 우회였다.

`async`와 `await`에 대한 책의 설명도 이 구조 위에서 읽어야 한다. `await runner.inference.async_run(...)`은 API 서버가 Runner의 응답을 기다리는 동안 다른 요청을 받게 해 줄 뿐, 계산을 빠르게 하지는 않는다. Runner가 하나이고 메서드가 `batchable=False`이면 동시에 들어온 요청은 Runner 앞에 줄을 선다. [B-4](#ch10-b-4)에서 동시 요청을 1개에서 8개로 늘리자 처리량은 초당 25.9건에서 33.1건으로 조금 늘었지만, p95 지연은 51ms에서 1,149ms로 뛰었다.

여러 Runner를 `asyncio.gather`로 함께 부르는 책의 예시(그레이스케일 변환 뒤 두 탐지 모델 비교)도 원리는 같다. 서로 다른 Runner가 서로 다른 프로세스에서 돌 때만 병렬이 되고, 단계 사이의 데이터 전달 비용은 그대로 남는다.

### 책의 BentoML 버전과 지금의 API {#bentoml-versions}

책 10.3은 `pip install bentoml==1.1.6`으로 시작하고, 10.3~10.5의 탐지 서비스는 1.1의 `bentoml.Runnable`, `bentoml.Runner`, `bentoml.Service`, `bentoml.io`를 쓴다. 그런데 10.6의 리스팅 10.1(추천 서비스)은 `@bentoml.service`를 붙인 클래스와 `@bentoml.api` 메서드를 쓴다. BentoML 1.2에서 들어온 새 API다. 클래스의 `__init__`이 Runner 생성자 역할을 하고, 메서드가 곧 API가 되며, 입출력 형식은 파이썬 타입 힌트로 정해진다. 1.1.6에는 이 API가 없으니 책의 두 코드는 한 환경에서 함께 돌 수 없다.

이번 실습은 두 코드를 각자의 버전으로 돌렸다. 탐지 서비스는 1.1 계열, 추천 서비스는 1.4.40이다. 1.4.40에서 `bentoml.Runnable`과 `bentoml.Runner`를 부르면 `bentoml.legacy`로 옮겨졌고 이후 제거될 예정이라는 경고가 뜬다. `bentoml.io`를 가져오면 1.4부터 사용 중단이라는 경고가 뜬다. 지금 새로 시작한다면 리스팅 10.1의 클래스 방식을 기준으로 삼는 게 맞다.

1.1 계열 안에서도 책의 1.1.6 대신 1.1.10을 썼다. 1.1.6은 `cattrs`의 상한을 두지 않아서 지금 설치하면 `cattrs 26.2.1`이 깔린다. 이 조합에서는 `bentoml build`가 `bento.yaml`에 이름과 버전을 쓰지 않는다. 그 결과 만든 Bento를 `bentoml list`도 `bentoml serve`도 `KeyError: 'name'`으로 읽지 못했다. 빌드는 성공했다고 나오는데 결과물을 못 읽으니, 원인이 잘 보이지 않는 종류의 실패다. 1.1.10은 `cattrs<23.2.0`으로 고정한다.

## 요청 검증과 응답 계약 {#request-contract}

서비스의 API는 다른 팀과 맺은 약속이다. "이미지를 보내면 탐지된 신분증마다 클래스, 신뢰도, 박스를 돌려준다", "사용자 ID를 보내면 아직 안 본 영화 ID를 점수 순으로 돌려준다" 같은 문장이 계약이고, 서비스 코드는 이 문장을 지켜야 한다. 저자 코드를 실제로 돌려 보면 정상 경로의 200 응답 뒤에 계약 위반이 숨어 있다. 이 장에서 가장 놀란 대목이다.

탐지 서비스는 **첫 박스만 돌려준다**. `results = self.model(input_img)[0]`로 첫 이미지의 결과를 꺼낸 뒤 다시 `results[0]`을 JSON으로 바꾸는데, 두 번째 인덱싱이 고르는 것은 이미지가 아니라 박스다. 신분증 두 장을 붙인 이미지에서 모델은 박스 두 개를 찾았지만 `/invocation`은 하나만 돌려줬다. 같은 이미지로 부른 `/render`에는 박스가 두 개 그려져 있으니, 두 엔드포인트가 서로 다른 답을 내는 셈이다.

아무것도 못 찾으면 500이 난다. 박스가 없는 이미지에서 `results[0]`이 `IndexError`를 내고 응답은 500이 된다. "신분증이 없다"는 정상적인 답이 서버 오류로 바뀐다. `/render`는 `save=True, project=os.getcwd()` 때문에 요청마다 `predict`, `predict2`, `predict3`... 폴더를 작업 디렉터리에 남긴다. 컨테이너에서는 쓰기 계층이 계속 커지고, 동시에 요청이 오면 폴더 번호를 두고 경쟁한다.

추천 서비스의 문제는 더 조용하다. 9장의 학습 코드는 `userId - 1`, `movieId - 1`을 임베딩 행으로 썼는데, 저자 서비스는 `user_id`를 그대로 쓰고 후보를 `torch.arange(1, n_items + 1)`로 만든다. 사용자 50의 점수는 사용자 51의 임베딩으로 매겨지고, 돌려준 ID `k`는 실제로는 영화 `k + 1`의 점수다. 학습과 서빙의 전처리가 어긋나는 전형적인 training-serving skew다.

후보 범위도 틀렸다. 9장에서 본 것처럼 `n_items`는 영화 수(9,742)가 아니라 최대 ID(193,609)다. 1부터 193,609까지 모든 정수를 후보로 쓰니 대부분이 카탈로그에 없는 ID다. 실습에서 사용자 50의 상위 5개 중 4개(132269, 123347, 89636, 89459)가 영화 목록에 없었다. 범위 밖 입력도 500이다. 없는 사용자 ID(99999)나 음수를 보내면 임베딩 인덱스 오류가 나서 500을 돌려준다. 클라이언트의 잘못이 서버 오류로 집계되면 오류율 지표까지 오염된다.

고친 서비스는 이 계약을 코드로 적는다. 탐지 서비스는 모든 박스를 돌려주고, 없으면 빈 목록을 돌려준다. 결과 이미지는 메모리에서 그리고, 너무 큰 이미지는 400으로 거절한다. 추천 서비스는 학습과 같은 인덱스를 쓰고, 후보를 카탈로그의 영화로 제한하고, 사용자 ID와 `top_k`가 범위를 벗어나면 400을 돌려준다.

고친 추천 서비스가 사용자 50과 모델 v1에 대해 내놓은 상위 5개(115727, 103228, 122902, 59604, 63433)는 9장의 [F-3](../09-training-and-validation-2/#ch09-f-3)에서 별도 평가 스크립트로 구한 목록과 같았다. 서빙 경로가 학습 쪽 평가와 같은 답을 내는지 맞춰 보는 것이 단위 테스트보다 먼저 할 계약 시험이다.

입력 타입 검사는 도구가 일부 맡아 준다. BentoML 1.1의 `Image()`는 허용하지 않은 MIME 형식이나 디코딩할 수 없는 바이트를 400으로 거절했다. 1.4의 타입 힌트(`user_id: int`)는 문자열이 들어오면 pydantic 검증 오류와 함께 400을 돌려줬다. 하지만 "이 사용자가 학습에 있었는가", "이 이미지가 처리할 만한 크기인가" 같은 의미 검사는 서비스 코드가 해야 한다.

## 상태 확인과 지표 {#health-and-metrics}

Kubernetes가 Pod를 관리하려면 두 질문에 답하는 경로가 필요하다. 살아 있는가(liveness), 그리고 지금 요청을 받아도 되는가(readiness)다. liveness가 실패하면 kubelet이 컨테이너를 재시작하고, readiness가 실패하면 Service가 그 Pod로 요청을 보내지 않는다. 모델 로딩처럼 시작이 느린 서비스에서 둘을 섞으면 위험하다. 로딩 중인 Pod를 죽었다고 보고 재시작하면 영영 준비 상태에 이르지 못한다.

BentoML은 `/livez`, `/readyz`, `/healthz`, `/metrics`를 기본으로 제공한다(책의 그림 10.7, 10.8). 서비스를 띄우고 0.3초 간격으로 두 경로를 찔러 보니, 탐지 서비스는 연결 자체가 거부되다가 두 경로가 동시에 200이 됐다. 걸린 시간은 PC 부하에 따라 10초에서 30초까지 달랐다. 추천 서비스도 18.2초 뒤 동시에 200이 됐다. 이번 로컬 실행에서는 살아 있지만 준비되지 않은 구간이 보이지 않았던 셈이다.

포트가 열리기 전의 시간은 Kubernetes 프로브가 보기에 실패다. 그래서 liveness 프로브에는 넉넉한 `initialDelaySeconds`나 `startupProbe`가 필요하다. KServe에 올린 예측 컨테이너는 반대로 포트를 먼저 열고, 모델 로딩과 예열이 끝난 뒤에야 모델 상태 경로가 200을 돌려주게 했다. 두 질문을 서로 다른 경로로 나눈 것이다.

`/metrics`는 요청 수와 지연을 엔드포인트, 응답 코드, 서비스 버전 라벨과 함께 내놓는다. 소스 폴더에서 띄우면 `service_version="not available"`이고, Bento 태그로 띄우면 `service_version="rxu4w6w3dcwsplaz"`처럼 Bento 버전이 붙는다. 실행 중인 패키지 버전이 지표에 같이 남으니 출시 기록과 이어 볼 수 있다. 다만 이 값은 Bento 버전이지 모델 버전이 아니다. 책이 말하는 모델 성능 모니터링은 이 지표만으로는 안 되고, 예측과 나중에 들어오는 정답을 잇는 11장의 일이 따로 필요하다.

## 배치와 지연 {#batching-latency}

책은 BentoML의 장점으로 적응형 마이크로배칭을 든다. 짧은 시간 안에 들어온 요청을 모아 모델을 한 번에 부르면, 행렬 연산을 묶어 처리하는 가속기의 효율이 올라 처리량이 는다. 대신 먼저 온 요청은 다른 요청이 모일 때까지 기다리니 지연이 늘 수 있다. 그래서 배칭 설정은 늘 두 값으로 이뤄진다. 최대 몇 개까지 모을지, 최대 얼마나 기다릴지다.

이번 실습의 서비스는 저자 코드대로 `batchable=False`다. 같은 이미지로 40건씩 보낸 결과는 아래와 같다(CPU, API 서버 2개, Runner 1개).

| 동시 요청 | p50 | p95 | 처리량 |
| --- | --- | --- | --- |
| 1 | 36.0ms | 50.8ms | 25.9건/초 |
| 4 | 64.3ms | 430.9ms | 30.5건/초 |
| 8 | 59.6ms | 1,149.4ms | 33.1건/초 |

동시 요청을 늘려도 처리량은 거의 그대로이고 꼬리 지연만 커진다. Runner 하나가 이미지를 한 장씩 처리하는 동안 나머지는 대기열에서 기다리기 때문이다. 배칭을 켜면 이 대기를 묶음 처리로 바꿀 수 있지만, CPU에서 YOLO가 묶음으로 얼마나 이득을 보는지는 이번에 재지 않았다. 용량을 넘는 요청은 무한정 줄 세우기보다 빨리 실패시키는 편이 낫다. 시간 제한(1.4 서비스의 `traffic={"timeout": 10}`)과 동시 요청 제한을 두면 호출하는 쪽이 재시도나 대체 경로를 고를 수 있다.

## Bento는 무엇을 고정하고 무엇을 고정하지 않는가 {#bento-and-image}

`bentofile.yaml`에는 진입점이 될 서비스 객체, 포함할 파일, 파이썬 패키지와 기반 이미지를 적는다. `bentoml build`는 이 내용과 생성한 Dockerfile을 묶어 `yolo_v8:rxu4w6w3dcwsplaz` 같은 태그를 붙인다. 책 10.5.1의 말대로 태그를 생략하고 `latest`를 쓰면 같은 명령이 시점마다 다른 Bento를 가리킨다. 배포와 기록에는 항상 전체 태그를 쓴다.

Bento가 실제로 무엇을 고정하는지는 저자의 두 `bentofile.yaml`을 나란히 놓으면 드러난다.

탐지 서비스의 bentofile은 가중치 파일을 `include`로 넣고 `ultralytics/ultralytics:8.0.203-cpu`를 기반 이미지로 지정할 뿐, 파이썬 패키지는 적지 않는다. 생성된 Dockerfile은 그 이미지 위에 BentoML만 설치한다. 그러면 실제 ultralytics 버전은 기반 이미지가 정하게 된다(8.0.203). 저장소의 `requirements.txt`(8.0.194)와도, 우리 가중치를 학습한 버전(8.3.56)과도 어긋난다. Bento의 `models: []`도 비어 있다. 가중치가 BentoML 모델 저장소의 모델이 아니라 그냥 소스 파일로 들어갔기 때문이다.

추천 서비스의 bentofile은 `requirements.txt`에 `torch`, `mlflow`를 버전 없이 적는다. BentoML 1.4는 빌드할 때 의존성을 Linux용으로 잠근다. 그대로 빌드하자 `torch==2.8.0`과 함께 `nvidia-cublas-cu12` 같은 CUDA 패키지 15개와 `triton`이 잠겼다. PyPI의 Linux용 torch가 CUDA 빌드라서다. CPU로만 서빙할 이미지에 수 GB의 GPU 라이브러리가 따라 들어가는 셈이다. CPU 휠의 주소를 직접 적자 `nvidia-ml-py`(BentoML 자체 의존성) 하나만 남았다.

가장 큰 차이는 추천 Bento에 **모델이 없다**는 점이다. 서비스가 시작할 때 MLflow에서 별칭을 읽어 내려받으므로, Bento 태그가 같아도 언제 시작했느냐에 따라 다른 모델이 뜬다.

결국 Bento는 "이 코드를 이 의존성으로 실행하라"는 묶음이다. 그 안에 모델이 들어 있는지는 서비스를 어떻게 썼느냐에 달렸다. 모델까지 고정하려면 BentoML 모델 저장소로 가져온 모델을 서비스에서 참조해 Bento에 포함시키거나, 이번 탐지 서비스처럼 가중치와 버전 정보 파일(`model_info.json`)을 함께 넣는다.

컨테이너 이미지(`bentoml containerize`)는 만들지 않았다. 디스크 여유가 2~7GB를 오가는데 torch가 든 이미지를 빌드해 kind 노드에 적재하면, Docker 디스크가 수 GB 늘어 다른 작업까지 멈출 수 있었다. 대신 생성된 Dockerfile을 읽었다. 고친 탐지 Bento는 `FROM python:3.10-slim`에 `libgl1`, `libglib2.0-0`과 고정한 패키지를, 추천 Bento는 `FROM python:3.9-slim`에 uv로 잠근 목록을 설치한다. 둘 다 3000번(API)과 3001번(Prometheus) 포트를 연다. 이미지 digest는 빌드해야 생기는 값이라, 출시 기록에는 KServe가 실행한 기존 이미지의 ID를 대신 적었다.

## BentoML과 MLflow를 함께 쓸 때 {#bentoml-mlflow}

책 10.6은 MLflow 레지스트리의 `prod` 별칭으로 모델을 찾는 추천 서비스를 만든다. 역할 분담은 자연스럽다. MLflow는 어떤 실행이 어떤 지표를 냈고 지금 어느 버전을 쓰기로 했는지 기록하고, BentoML은 그 버전을 요청 경로에 올린다. 별칭을 쓰면 서비스 코드는 버전 번호를 몰라도 되고, 레지스트리에서 별칭을 옮기는 일이 곧 배포 결정이 된다.

막상 돌려 보면 이 연결에는 조건이 여럿 붙는다.

먼저 걸리는 것은 **별칭이 시작할 때 한 번만 해석된다**는 점이다. [D-6](#ch10-d-6)에서 서비스가 v2로 떠 있는 동안 `prod`를 v1로 옮겼는데, 같은 프로세스는 계속 v2로 응답했다. 재시작한 뒤에야 v1이 떴다. 별칭 이동은 다음에 시작할 서비스에 대한 결정인 셈이다. 복제본 여럿이 다른 시점에 재시작하면 서로 다른 버전이 섞여 응답할 수도 있다. 그래서 고친 서비스는 해석한 버전을 로그에 남기고, 모든 응답에 `x-model-version` 헤더로 붙인다. 출시 기록에도 별칭이 아니라 이 해석된 버전을 적는다. 운영에서는 `MODEL_VERSION`으로 버전을 고정해 시작할 수도 있게 했다.

실행 시점 의존성도 생긴다. 서비스는 시작할 때마다 MLflow 서버와 S3에 접속해야 한다. MLflow가 잠시 멈추면 이미 떠 있는 Pod는 괜찮지만 새 Pod는 뜨지 못한다. 확장이나 재시작이 가장 필요한 순간에 실패할 수 있다는 뜻이다.

저자 코드는 시작할 때마다 모델을 복사하기도 한다. `bentoml.mlflow.import_model`로 모델을 BentoML 저장소에 새로 가져온 뒤 `recommender:latest`를 읽는 방식이라, 두 번 시작하자 `recommender:kbjzhn63cs65hlaz`와 `recommender:tte63hw3csmwtlaz`, 같은 14.85MiB 모델이 두 벌 쌓였다. 고친 서비스는 `mlflow.pytorch.load_model`로 바로 읽는다.

파이썬 버전도 모델의 일부다. 9장의 학습 컴포넌트는 Python 3.9에서 돌았고, `mlflow.pytorch`는 모델 클래스의 바이트코드까지 직렬화한다. 그래서 추천 서비스 환경도 Python 3.9로 맞췄고, Bento의 기반 이미지도 `python:3.9-slim`이어야 한다.

설정값이 코드에 박혀 있는 것도 문제였다. 저자 코드는 MLflow 주소를 저자 집의 IP(`192.168.1.90:8080`)로 적었다. 책은 `registered_model_name`을 생성자 인자로 설명하지만, 1.2 이후 서비스 클래스는 인자 없이 생성되니 그 값을 바꿀 길이 없다. 고친 서비스는 둘 다 환경 변수로 받는다. 같은 파일의 Prometheus 카운터 두 개는 같은 이름(`ranked_movie_present_counter`)으로 등록돼 있어서, 저자 서비스는 시작하자마자 `DuplicateTimeseries`로 죽었다.

## MLflow만으로 서빙하기 {#mlflow-only}

책 10.7은 도구 하나를 줄이는 길도 보여 준다. `mlflow models serve -m "models:/<이름>@prod"`는 등록된 모델을 `/invocations`(예측), `/ping`, `/health`(상태), `/version` 경로를 가진 HTTP 서버로 띄운다. 서빙 방식은 모델의 pyfunc 인터페이스가 정한다. MLflow는 프레임워크별 flavor를 "데이터프레임이나 배열을 받아 예측을 돌려주는 함수" 하나로 감싸고, 서버는 그 함수를 부른다.

이 단순함이 이번 추천 모델과는 맞지 않았다. 9장의 모델은 `forward(user, item)`으로 입력 두 개를 받고, 서명도 `user`, `movie` 두 텐서로 기록돼 있다. 그런데 PyTorch flavor의 pyfunc는 텐서 하나(데이터프레임이나 배열)만 넘긴다. [E-1](#ch10-e-1)에서 사전 형식으로 보내면 `TypeError: The PyTorch flavor does not support List or Dict input types`가, 배열로 보내면 `Model is missing inputs ['user', 'movie']`가 났다. 서버는 떴고 `/ping`도 200이었지만 어떤 입력으로도 예측할 수 없었다.

더 근본적인 문제도 있다. "사용자에게 영화 10편 추천"은 모델을 한 번 부르는 일이 아니다. 후보를 만들고, 점수를 매기고, 정렬하는 절차라서 이 절차를 어딘가에 써 넣어야 한다.

MLflow에서 그 자리는 `mlflow.pyfunc.PythonModel`이다. 원래 PyTorch 모델과 영화 카탈로그를 아티팩트로 담고, `predict`가 `user_id`, `top_k` 열을 받아 추천 목록을 돌려주는 래퍼 모델을 새로 기록해 등록한다. 그러면 `mlflow models serve`가 그대로 서빙한다. BentoML 서비스의 `predict`에 쓴 로직을 MLflow 모델 안으로 옮긴 셈이다.

차이도 분명하다. 응답에 모델 버전 헤더를 붙이거나 입력 오류를 400과 짧은 메시지로 돌려주는 식의 HTTP 수준 제어가 없다. 오류 응답에는 서버의 파일 경로가 담긴 `stack_trace`가 그대로 실려 나갔다. 외부에 노출할 서비스라면 앞단에서 걸러야 한다. 책이 소개하는 `mlflow models build-docker --enable-mlserver`는 같은 모델을 Seldon MLServer 기반 이미지로 만드는 명령인데, 디스크 사정으로 이번에는 실행하지 않았다.

## KServe: 배포를 선언으로 맡기기 {#kserve}

여기까지는 서비스를 어떻게 만들지의 이야기였다. 만든 서비스를 클러스터에 몇 개 띄우고, 상태를 살피고, 새 버전으로 바꾸고, 문제가 생기면 되돌리는 일은 따로 누군가 맡아야 한다. 6장에서는 Yatai가 그 역할이었다. KServe는 같은 일을 `InferenceService`라는 Kubernetes 커스텀 리소스 하나로 선언하게 한다. 사용자가 "이 이미지(또는 이 모델 형식과 저장 위치)를 이 자원과 이 프로브로 띄워라"라고 적으면, 나머지 리소스는 KServe 컨트롤러가 만든다.

KServe에는 두 가지 배포 모드가 있다.

| 모드 | 만드는 것 | 필요한 구성 요소 | 얻는 것 |
| --- | --- | --- | --- |
| Serverless(Knative) | Knative Service와 Revision | Knative Serving, Istio 같은 네트워크 계층 | 요청이 없으면 0개로 축소, 리비전 단위 트래픽 분할 |
| Standard(이전 이름 RawDeployment) | Deployment, Service, HPA | 없음(Kubernetes 기본 리소스) | 단순한 구조, 기존 운영 도구와 호환 |

이번에는 Knative와 Istio를 설치하지 않으려고 Standard 모드를 썼다. `InferenceService` 하나를 적용하자 `ch10-detector-predictor`라는 Deployment, Service, HPA가 생겼다. HPA의 CPU 사용률은 kind에 metrics-server가 없어 `<unknown>`으로 남았다. 0개 축소나 리비전별로 트래픽을 나누는 카나리는 Knative 쪽 기능이라 이 모드에서는 시험하지 않았다.

모델 서버를 KServe가 고르게 할 수도 있다. `predictor.model.modelFormat.name`에 `sklearn`, `xgboost`, `pytorch` 같은 형식을, `storageUri`에 모델 위치를 적으면 컨트롤러가 그 형식을 지원하는 `ClusterServingRuntime`의 이미지를 띄운다. 책의 예시가 이 방식인데, YOLO PyTorch 모델에 `sklearn`을 지정했다. 형식을 맞춰도 KServe의 PyTorch 런타임은 TorchServe라 `.mar` 아카이브를 기대하므로 `best.pt`를 그대로 올릴 수 없다. [F-5](#ch10-f-5)에서 책의 명세를 적용하자, 서빙 런타임을 넣지 않은 이번 설치에서는 `no runtime found to support predictor with model type: {sklearn <nil>}`가 남고 READY는 `Unknown`에 머물렀다.

그래서 탐지 모델은 **사용자 정의 컨테이너**로 올렸다. KServe는 컨테이너가 정해진 포트로 요청을 받기만 하면 된다. kind 노드에 있던 `ultralytics/ultralytics:8.3.56-cpu` 이미지에서, 표준 라이브러리로 만든 작은 서버가 KServe V1 프로토콜(`GET /v1/models/<이름>`, `POST /v1/models/<이름>:predict`)을 따른다. 환경 변수에 `STORAGE_URI`를 주면 KServe가 `storage-initializer` 초기화 컨테이너를 붙여 S3의 가중치를 `/mnt/models`로 내려받는다. 운영이라면 kserve SDK의 `kserve.Model`로 서버를 쓰고 이미지를 따로 빌드하겠지만, 디스크가 모자라 기존 이미지와 ConfigMap으로 넣은 코드로 대신했다.

책은 "KServe는 Kubeflow와 함께 온다"고 하지만, 이번 환경처럼 Kubeflow Pipelines만 설치했다면 KServe는 없다. KServe는 Kubeflow 전체 설치에 들어가는 별도 구성 요소이고, 따로 설치할 수도 있다. 이번에는 KServe v0.21.0의 공식 매니페스트에서 InferenceService 컨트롤러만 남기고 LLM용 컨트롤러와 로컬 모델 캐시 구성 요소는 뺐다. cert-manager는 6장에서 설치한 v1.13.3를 그대로 썼고, 웹훅 인증서도 문제없이 발급됐다.

## 세 도구가 맡는 범위 {#tool-boundaries}

책의 표 10.1은 KServe, BentoML, MLflow를 초점과 쉬움으로 비교한다. 직접 써 보니 셋은 같은 일을 두고 경쟁한다기보다 서로 다른 층을 맡는다. 아래 표는 이번 실습에서 각 도구가 실제로 맡은 일이다.

| 일 | BentoML | MLflow 서빙 | KServe |
| --- | --- | --- | --- |
| 입력 검증과 전처리 코드 | 서비스 메서드에 직접 쓴다 | pyfunc 래퍼의 `predict`에 쓴다 | 컨테이너 안의 서버나 런타임이 한다 |
| 모델 로딩 | `__init__`이나 Runner 생성자 | flavor가 정한 방식 | 런타임이나 사용자 코드, 파일은 storage-initializer가 가져온다 |
| API 문서와 상태 경로 | Swagger, `/livez`, `/readyz`, `/metrics` 기본 제공 | `/ping`, `/health`, `/version` | V1, V2 프로토콜의 모델 상태 경로 |
| 패키징 | Bento와 잠근 의존성, Dockerfile | 모델 폴더의 `python_env.yaml`, `build-docker` | 하지 않는다. 이미지는 이미 있어야 한다 |
| 클러스터 배포와 확장 | 하지 않는다(Yatai나 직접 작성한 Deployment) | 하지 않는다 | Deployment, Service, HPA를 만들고 상태를 모은다 |
| 버전 기록 | Bento 태그, 지표의 `service_version` | 레지스트리 버전과 별칭 | 리소스 명세와 generation |

조합하는 기준도 여기서 나온다. 탐지 결과를 그리는 `/render`나 후보를 골라 정렬하는 추천처럼 전처리와 후처리가 많은 모델에는 서비스 코드를 쓰기 편한 BentoML이 맞다. 입력 하나에 예측 하나인 표준 모델이라면 MLflow나 KServe 기본 런타임으로 충분하다. 클러스터 배포를 선언적으로 관리하고 싶다면 KServe에 맡기면 되고, 그 안에서 도는 컨테이너는 BentoML로 만든 이미지여도 된다.

## 출시 정보와 롤백 단위 {#release-and-rollback}

출시 기록은 "지금 이 요청에 답한 것이 정확히 무엇인가"에 답할 수 있어야 한다. 앞의 다섯 층에 맞추면 모델 버전과 가중치 해시, 서비스 코드의 해시나 커밋, 패키지 태그, 이미지 digest, 배포 명세가 필요하다. 아래는 [F-7](#ch10-f-7)에서 클러스터와 MLflow에 실제로 물어 만든 기록이다. 손으로 적은 값은 없다.

```yaml
release_id: ch10-detector-r1
previous_release_id: none
inference_service: ch10-serving/ch10-detector
isvc_generation: 3
image: ultralytics/ultralytics:8.3.56-cpu
image_id:
- sha256:1b5f10d4f9628c8a7a5d3094adbdd68facc3536ec8622f2e1bb8e5dff7e3a443
server_code_sha256: 0940ab938a24b95500a6e5b52f557015f7c64a760b392f8d1e7af4b0990620ca
storage_uri: s3://ch10-models/detector/ch08-id-card-detector/1
model:
  registry_name: ch08-id-card-detector
  version: '1'
  run_id: 74f605c4bb544d50bf88abf3500c587b
  weights_sha256: d8c5a0d2bf8f7207f95166cfd41b8610d2038a0a698008c6c9682e7f029791a9
  release_decision: hold
api_contract: KServe V1 /v1/models/ch10-detector:predict, instances[].image_b64
ready:
- IngressReady=True
- PredictorReady=True
- Ready=True
- Stopped=False
```

`image_id`는 레지스트리의 digest가 아니라 노드가 가진 이미지의 ID다. 9장에서 `kind load`로 노드에 직접 넣은 이미지라 레지스트리 digest가 없다. 운영에서는 레지스트리에 올린 이미지를 `image@sha256:...` 형식으로 지정해야 노드가 바뀌어도 같은 파일이 뜬다. `release_decision: hold`는 8장의 판단이 그대로 따라온 값이다. 기록에 이 값이 함께 보이지 않으면 보류된 모델이 서빙되고 있다는 사실이 묻힌다.

롤백 단위는 이 기록 전체다. [F-6](#ch10-f-6)에서 저장 위치를 존재하지 않는 버전 2로 바꾼 명세(r2)를 적용했다. 새 Pod는 `storage-initializer`에서 `No model found`로 실패해 `Init:CrashLoopBackOff`에 머물렀고, Deployment의 롤링 업데이트는 기존 Pod를 내리지 않았다. 요청은 계속 v1이 처리했다.

이 장에서 가장 조심할 대목은 그동안 `kubectl get inferenceservice`가 내내 `READY True`였다는 점이다. KServe의 Ready는 최소 가용 복제본이 있다는 뜻이다. 마지막에 적용한 명세가 반영됐다는 뜻은 아니다. 새 릴리스가 실제로 반영됐는지는 `kubectl rollout status`나 Deployment의 `updatedReplicas`, 그리고 응답의 `x-model-version`으로 확인해야 한다. 이전 명세(r1)를 다시 적용하자 Deployment는 같은 Pod 템플릿으로 돌아가, 기존 Pod는 그대로 둔 채 실패한 ReplicaSet을 0으로 줄였다.

MLflow 별칭으로 모델을 고르는 추천 서비스에서는 롤백이 두 단계다. 별칭을 이전 버전으로 옮기고, 서비스를 다시 시작한다. 별칭만 옮기면 아무 일도 일어나지 않고(D-6), 재시작만 하면 옮기지 않은 별칭을 다시 읽는다. 코드나 전처리가 함께 바뀐 릴리스라면 모델만 되돌려서도 안 된다. 고친 추천 서비스는 학습과 같은 인덱스를 쓰도록 바뀌었으니, 서비스를 저자 코드로 되돌리고 모델만 그대로 두면 다시 엉뚱한 영화를 추천한다. 모델, 전처리, 코드, 의존성이 맞물린 조합을 한 단위로 되돌릴 수 있게 기록해야 하는 이유다.

출시 전에 보낼 요청도 같은 관점에서 정한다. 정상 입력의 200만으로는 부족하다. 이번 실습에서 실제로 문제가 드러난 입력은 모두 넣어 본다. 박스가 여러 개인 이미지, 아무것도 없는 이미지, 이미지가 아닌 바이트, 너무 큰 이미지, 학습에 없던 사용자, 범위 밖의 `top_k`, 그리고 서비스가 아직 준비되지 않았을 때의 요청이다. 응답 코드가 400인지 500인지, 응답에 어떤 버전이 찍히는지, 서버 로그에 무엇이 남는지를 함께 본다.

## 책 본문과 저자 코드의 차이 {#book-vs-code}

10장 코드는 별도 저장소가 아니라 8~9장 저장소의 `serving` 폴더에 있다. 탐지 서비스는 [object-detection-project](https://github.com/practical-mlops/object-detection-project)의 `serving/`(커밋 `c6afb11`), 추천 서비스는 [movie-recommender-project](https://github.com/practical-mlops/movie-recommender-project)의 `serving/`(커밋 `4e0a808`)이다.

| 위치 | 책과 저자 코드 | 실제로 일어나는 일 | 이 실습의 처리 |
| --- | --- | --- | --- |
| BentoML 버전 | 10.3은 1.1.6, 리스팅 10.1은 1.2 이후 API | 한 환경에서 두 코드가 함께 돌지 않는다. 1.1.6은 지금 설치하면 `cattrs 26`과 맞지 않아 빌드한 Bento를 읽지 못한다 | 탐지는 1.1.10(Python 3.10), 추천은 1.4.40(Python 3.9) |
| Runner 이름 | 책은 `name="yolov8_runnable"`을 주라고 한다 | 저자 코드는 이름을 주지 않아 `yolov8runnable`이라는 경고가 API 서버마다 찍힌다 | 이름 지정 |
| `/invocation` | `results[0].tojson()` | 첫 박스만 반환, 탐지가 없으면 `IndexError`로 500 | 모든 박스, 없으면 `[]` |
| `/render` | `save=True, project=os.getcwd()` | 요청마다 `predictN` 폴더가 쌓인다 | 메모리에서 그려 JPEG로 반환 |
| 탐지 bentofile | 기반 이미지 `ultralytics:8.0.203-cpu`, 패키지 목록 없음 | 실제 ultralytics 버전을 기반 이미지가 정하고, 저장소의 8.0.194와도 어긋난다 | `python:3.10-slim`과 고정한 패키지 목록 |
| 추천 서비스 주소 | `http://192.168.1.90:8080`, 책은 `http://mlflow:8080` | 저자 환경의 주소다 | `MLFLOW_TRACKING_URI` 환경 변수 |
| 모델 이름 | 생성자 인자 `registered_model_name` | 1.2 이후 서비스 클래스는 인자 없이 생성되어 바꿀 수 없다 | `MODEL_NAME`, `MODEL_ALIAS`, `MODEL_VERSION` 환경 변수 |
| `metrics.py` | 카운터 두 개 | 두 번째 카운터의 이름이 첫 번째와 같아 `DuplicateTimeseries`로 시작 실패 | 이름 수정 |
| 인덱스 | `user_id`, `arange(1, n_items + 1)` | 학습은 `- 1`을 썼다. 다른 사용자와 다른 영화의 점수가 나온다 | 학습과 같은 인덱스 |
| 후보 | 1부터 최대 ID까지 모든 정수 | 카탈로그에 없는 ID를 추천한다 | `ch09-datasets`의 영화 목록으로 제한 |
| 모델 가져오기 | 시작마다 `bentoml.mlflow.import_model` | 시작할 때마다 같은 모델이 저장소에 한 벌씩 쌓인다 | `mlflow.pytorch.load_model`로 직접 로딩 |
| 추천 requirements | `torch`, `mlflow` 버전 없음 | Linux 잠금에서 CUDA 패키지 15개가 따라온다 | CPU 휠 주소와 버전 고정 |
| MLflow만으로 서빙 | `mlflow models serve -m models:/recommender_production@prod` | 두 입력을 받는 PyTorch 모델은 pyfunc로 예측할 수 없다 | pyfunc 래퍼 모델 `ch10-recommender-pyfunc` |
| KServe 예시 | YOLO 모델에 `modelFormat: sklearn`, `gs://` 경로 | 런타임을 찾지 못한다. 형식이 맞아도 PyTorch 런타임은 `.mar`을 기대한다 | 사용자 정의 컨테이너와 `STORAGE_URI` |
| `prod` 별칭 | 9장 파이프라인이 만든다고 가정 | 9장 파이프라인은 `staging`만 만든다 | 9장 버전을 복사한 `ch10-recommender`에 `prod`를 직접 지정 |

## 이 장이 남기는 한계 {#remaining-limits}

이 장에서는 두 모델을 세 가지 방식으로 요청 경로에 올리고, 클러스터에 선언적으로 배포했다가 되돌리는 데까지 해 봤다. 남은 일도 분명하다.

컨테이너 이미지를 빌드하지 못해서 `bentoml containerize`와 `docker run`, 이미지 digest로 고정한 배포는 확인하지 못했다. KServe에는 노드에 이미 있던 이미지를 썼다. 탐지 서비스는 배칭을 켜지 않았고, 부하 시험은 한 PC에서 같은 이미지를 반복한 수준이다. 콜드 스타트, 큰 입력의 메모리, 포화 상태의 시간 제한은 재지 않았다. KServe의 Serverless 모드, 카나리 트래픽 분할, 0개 축소, 기본 서빙 런타임도 설치하지 않아 시험하지 못했다.

모델 쪽 한계도 있다. 서빙한 탐지 모델은 8장에서 출시 보류된 버전이고, 추천 모델은 9장에서 인기순 기준선보다 크게 낮았던 버전이다. 서비스가 정상 응답한다는 것과 모델이 쓸 만하다는 것은 별개다. 응답에 모델 버전을 붙였지만 요청과 예측을 저장하지는 않는다. 입력 분포의 변화, 나중에 들어오는 정답과의 비교, 예측 설명은 11장의 몫이다.

## 실습 순서 {#book-ch10-sop}

책의 순서를 따른다. 탐지 서비스를 BentoML로 띄워 Bento로 묶고, 추천 모델을 MLflow와 연결해 서빙한 뒤, MLflow만으로도 서빙해 본다. 마지막으로 KServe로 클러스터에 배포했다가 되돌린다. 아래 출력과 화면은 2026년 11월 8일에 이 순서대로 실행해 얻은 것이다.

```mermaid
flowchart LR
    accTitle: 10장 실습 순서
    accDescr: 환경과 저자 코드를 준비한 뒤 BentoML 1.1 탐지 서비스를 저자 코드와 고친 코드로 실행하고 Bento로 빌드한다. 이어 9장 추천 모델을 MLflow 별칭으로 읽는 BentoML 1.4 서비스와 MLflow 단독 서빙을 확인한다. 마지막으로 KServe를 설치해 탐지 모델을 InferenceService로 배포하고 잘못된 릴리스를 되돌린 뒤 정리한다.
    A["A. 환경과 코드 준비"] --> B["B. BentoML 탐지 서비스"]
    B --> C["C. Bento 빌드"]
    A --> D["D. BentoML과 MLflow<br/>추천 서비스"]
    D --> E["E. MLflow만으로 서빙"]
    B --> F["F. KServe 배포와 롤백"]
    C --> G["G. 문제 해결과 정리"]
    E --> G
    F --> G
```

| 구간 | 끝났을 때 남는 것 |
| --- | --- |
| A. 환경과 코드 준비 | 저자 코드 두 저장소, 가상환경 두 개, MLflow의 8장과 9장 모델 확인 |
| B. BentoML 탐지 서비스 | `ch10\yolo-fixed\`의 가중치와 `model_info.json`, 저자 서비스와 고친 서비스의 응답 비교 |
| C. Bento 빌드 | Bento `yolo_v8:<태그>` 두 개, Bento 태그로 띄운 서비스의 지표 |
| D. BentoML과 MLflow 추천 서비스 | 등록 모델 `ch10-recommender` v1, v2와 `prod` 별칭, 고친 추천 서비스, Bento `recommender_service:<태그>` |
| E. MLflow만으로 서빙 | 등록 모델 `ch10-recommender-pyfunc` v1과 `prod` 별칭, `/invocations` 응답 |
| F. KServe 배포와 롤백 | `kserve` 네임스페이스의 컨트롤러, `ch10-models` 버킷, `ch10-serving`의 `ch10-detector`, 출시 기록 |
| G. 문제 해결과 정리 | 멈춘 서버와 지운 리소스, 남겨 둘 기록 |

B, C와 D, E는 서로 독립이고, F는 B-1의 가중치만 있으면 된다. 명령은 [ml-platform-book-env](https://github.com/johklo/ml-platform-book-env) 저장소 최상위 폴더의 PowerShell에서 실행한다고 가정한다. 이 장에서 만드는 파일은 `ch10\`, 저자 코드는 `upstream\`에 둔다. 서버를 띄우는 명령은 별도 터미널에서 실행하고 `Ctrl+C`로 멈춘다.

## A. 환경과 코드 준비 {#ch10-a}

지금 위치는 전체 그림의 ①, ④를 준비하는 단계다. 8~9장이 레지스트리에 남긴 모델을 확인한다.

### A-1. 클러스터와 모델 확인 {#ch10-a-1}

1. 4장 [A-2, A-3](../04-experiments-features-pipelines/#book-lab-sop)과 같이 클러스터를 설치하고 두 번째 터미널에서 포트포워딩을 켜 둔다. MLflow(5000)와 S3 API(9000)를 쓴다.
   ```powershell
   python bookenv.py status
   python bookenv.py forward
   ```
2. http://localhost:5000 의 **Models**에 `ch08-id-card-detector`(8장 [G](../08-training-and-validation-1/#g-보충-mlflow-기록과-등록-결정))와 `ch09-recommender`(9장 [E-2](../09-training-and-validation-2/#ch09-e-2))가 있는지 본다. 이번 실습 시점의 상태는 아래와 같았다.

   | 등록 모델 | 버전 | 원천 | 태그와 별칭 |
   | --- | --- | --- | --- |
   | `ch08-id-card-detector` | 1 | `runs:/74f605c4.../train_run/weights` | `release_decision: hold`, `manual_review: fail: blur, small, dark` |
   | `ch09-recommender` | 1, 2 | run `615d3f32...`, `c1252d6c...` | `staging` → 2 |

   8장 모델의 원천은 MLflow 모델 형식이 아니라 가중치 폴더다. 레지스트리에 있어도 `mlflow models serve`로 바로 띄울 수는 없어서, 탐지 모델은 BentoML과 KServe로만 서빙한다.

### A-2. 저자 코드 {#ch10-a-2}

10장 코드는 8~9장 저장소의 `serving` 폴더에 있다. 9장에서 받은 저장소가 있어도, 9장에서 고친 파일과 섞이지 않게 새로 받는다.

```powershell
git clone https://github.com/practical-mlops/object-detection-project.git upstream/ch10-object-detection
git -C upstream/ch10-object-detection checkout c6afb11
git clone https://github.com/practical-mlops/movie-recommender-project.git upstream/ch10-movie-recommender
git -C upstream/ch10-movie-recommender checkout 4e0a808
```

탐지 쪽 `serving\`에는 `service.py`, `bentofile.yaml`, `requirements.txt`(ultralytics 8.0.194)와 저자가 학습한 `yolov8_custom.pt`가, 추천 쪽 `serving\`에는 `service.py`, `metrics.py`, `bentofile.yaml`, `requirements.txt`가 있다.

### A-3. 가상환경 두 개 {#ch10-a-3}

두 서비스가 쓰는 BentoML API와 파이썬 버전이 다르므로 환경을 나눈다.

1. 탐지 서비스용. BentoML 1.1 계열, 8장 실습과 같은 ultralytics와 torch를 쓴다.
   ```powershell
   uv venv .venv-ch10-yolo --python 3.10
   uv pip install --python .venv-ch10-yolo "bentoml==1.1.10" "setuptools<70" "click==8.1.7" `
       ultralytics==8.3.40 torch==2.5.1 torchvision==0.20.1 numpy==1.26.4 "opencv-python<4.12" `
       mlflow-skinny==3.0.0 boto3 `
       --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
   ```
   `setuptools<70`과 `click==8.1.7`은 6장 [A-4](../06-productionizing-models/#a-4-저자-코드와-python-310-가상환경)와 같은 이유다. 책의 1.1.6 대신 1.1.10을 쓰는 이유는 [앞에서 설명](#bentoml-versions)했다.
2. 추천 서비스용. 9장 학습과 같은 Python 3.9, PyTorch 2.8.0을 쓴다.
   ```powershell
   uv venv .venv-ch10-rec --python 3.9
   uv pip install --python .venv-ch10-rec bentoml==1.4.40 torch==2.8.0 mlflow==3.0.0 greenlet==3.1.1 boto3 pandas pyarrow
   ```
   Windows용 PyPI torch 휠은 CPU 빌드라 별도 인덱스가 필요 없다. 실습 당시 `download.pytorch.org`는 초당 40KB 안팎으로 느렸고 PyPI는 초당 1MB 이상이었다.
3. 두 환경 모두 BentoML 저장소를 이 실습 전용으로 쓰도록 터미널마다 지정한다.
   ```powershell
   $env:BENTOML_HOME = "$PWD\ch10\bentoml-home"
   $env:YOLO_CONFIG_DIR = "$PWD\ch10\yolo-config"
   ```

완료 기준: `.\.venv-ch10-yolo\Scripts\bentoml.exe -v`가 `1.1.10`, `.\.venv-ch10-rec\Scripts\python.exe -c "import bentoml, torch; print(bentoml.__version__, torch.__version__)"`가 `1.4.40 2.8.0+cpu`를 출력한다.

## B. BentoML 탐지 서비스 {#ch10-b}

지금 위치는 전체 그림의 ①~②다. 책 10.3~10.4를 따라간다.

### B-1. 레지스트리에서 가중치 가져오기 {#ch10-b-1}

책은 `yolov8_custom.pt`를 서비스 폴더에 두라고만 한다. 어느 버전인지 남기지 않으면 나중에 어떤 모델이 응답했는지 추적할 수 없으니, 가중치와 함께 버전 정보 파일을 만든다.

1. `ch10\fetch_detector.py`를 만든다.
   ```python
   import hashlib, json, os, sys
   os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://127.0.0.1:9000")
   os.environ.setdefault("AWS_ACCESS_KEY_ID", "minio")
   os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minio123")
   import mlflow
   from mlflow import MlflowClient

   name, version, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
   mlflow.set_tracking_uri("http://127.0.0.1:5000")
   mv = MlflowClient().get_model_version(name, version)
   path = mlflow.artifacts.download_artifacts(f"models:/{name}/{version}/best.pt", dst_path=out_dir)
   target = os.path.join(out_dir, "yolov8_custom.pt")
   os.replace(path, target)
   sha = hashlib.sha256(open(target, "rb").read()).hexdigest()
   info = {"registered_model": name, "version": mv.version, "run_id": mv.run_id,
           "source": mv.source, "tags": mv.tags, "sha256": sha}
   json.dump(info, open(os.path.join(out_dir, "model_info.json"), "w"), indent=2)
   print(json.dumps(info, indent=2))
   ```
2. 실행한다.
   ```powershell
   New-Item -ItemType Directory -Force ch10\yolo-fixed | Out-Null
   .\.venv-ch10-yolo\Scripts\python.exe ch10\fetch_detector.py ch08-id-card-detector 1 ch10\yolo-fixed
   ```
   ```text
   {
     "registered_model": "ch08-id-card-detector",
     "version": "1",
     "run_id": "74f605c4bb544d50bf88abf3500c587b",
     "source": "runs:/74f605c4bb544d50bf88abf3500c587b/train_run/weights",
     "tags": {"kfp_val_map50_95": "0.919", "manual_review": "fail: blur, small, dark", "release_decision": "hold"},
     "sha256": "d8c5a0d2bf8f7207f95166cfd41b8610d2038a0a698008c6c9682e7f029791a9"
   }
   ```
3. 시험 이미지를 준비한다. 8장 [F-2](../08-training-and-validation-1/#f-2-사전학습-모델과-학습-모델-비교)에서 학습에 쓰지 않은 표본을 모아 둔 `ch08\samples\`의 합성 신분증 두 장을 옆으로 붙여 카드가 두 장인 `ch10\two_cards.jpg`를 만들고, 카드가 없는 `neg01.jpg`, 5000x4000 단색 `huge.png`도 함께 쓴다.
   ```powershell
   .\.venv-ch10-yolo\Scripts\python.exe -c "from PIL import Image; a=Image.open('ch08/samples/clip02_f00.jpg'); b=Image.open('ch08/samples/clip00_f00.jpg'); c=Image.new('RGB',(a.width*2,a.height)); c.paste(a,(0,0)); c.paste(b,(a.width,0)); c.save('ch10/two_cards.jpg', quality=92); Image.new('RGB',(5000,4000),(90,140,120)).save('ch10/huge.png')"
   ```

### B-2. 저자 서비스 그대로 실행 {#ch10-b-2}

1. 저자의 `serving` 폴더를 복사하고 가중치만 B-1의 파일로 바꾼다.
   ```powershell
   New-Item -ItemType Directory -Force ch10\yolo-serving | Out-Null
   Copy-Item upstream\ch10-object-detection\serving\* ch10\yolo-serving\
   Copy-Item ch10\yolo-fixed\yolov8_custom.pt ch10\yolo-serving\ -Force
   cd ch10\yolo-serving
   ..\..\.venv-ch10-yolo\Scripts\bentoml.exe serve service.py:svc --port 3010
   ```
   10초 정도 뒤 `/readyz`가 200이 된다. 로그에는 `Using lowercased runnable class name 'yolov8runnable' for runner.`가 API 서버마다 찍힌다. 작업 관리자에서 보면 API 서버 프로세스 16개와 Runner 프로세스 1개가 떠 있다.
2. http://127.0.0.1:3010 의 Swagger UI에서 **POST /invocation → Try it out**을 누르고, 형식을 `image/jpeg`로 고른 뒤 `two_cards.jpg`를 올려 **Execute**한다. 카드가 두 장인데 박스가 하나만 온다.

   ![저자 서비스의 /invocation 응답. 카드가 두 장인 이미지에 박스 하나만 돌려준다.](/images/ml-platform-engineering/sop/ch10-b-author-invocation.png)

3. 같은 이미지를 **POST /render**로 보내면 응답 본문에 **Download file** 링크가 생긴다(책의 그림 10.5).

   ![저자 서비스의 /render 응답. output.jpeg 첨부 파일 링크와 응답 헤더.](/images/ml-platform-engineering/sop/ch10-b-author-render.png)

   내려받은 이미지에는 박스가 **두 개** 그려져 있다. 같은 모델, 같은 이미지인데 두 엔드포인트의 답이 다르다.
4. 다른 터미널에서 카드가 없는 이미지를 보낸다.
   ```powershell
   curl.exe -s -w " [%{http_code}]`n" -X POST -H "Content-Type: image/jpeg" --data-binary "@ch08\samples\neg01.jpg" http://127.0.0.1:3010/invocation
   ```
   ```text
   "" [500]
   ```
   서버 로그의 마지막 줄은 `IndexError: index 0 is out of bounds for dimension 0 with size 0`이다.
5. `/render`를 몇 번 부른 뒤 `ch10\yolo-serving`을 보면 `predict`, `predict2`, `predict3`... 폴더가 요청 수만큼 생겨 있다. 확인했으면 서버를 멈추고 이 폴더들을 지운다.

### B-3. 고친 서비스 {#ch10-b-3}

[요청 검증과 응답 계약](#request-contract)에서 정리한 문제를 고친다. 구조(Runner 하나, API 둘)와 엔드포인트 이름은 책과 같다.

`ch10\yolo-fixed\service.py`:

```python
import io
import json
import os

import bentoml
import PIL.Image
from bentoml.exceptions import BadInput
from bentoml.io import JSON, Image
from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_INFO = json.load(open(os.path.join(HERE, "model_info.json")))
MODEL_LABEL = f"{MODEL_INFO['registered_model']}/{MODEL_INFO['version']}"
MAX_PIXELS = 4096 * 4096


class YOLOv8Runnable(bentoml.Runnable):
    SUPPORTED_RESOURCES = ("cpu",)
    SUPPORTS_CPU_MULTI_THREADING = True

    def __init__(self):
        self.model = YOLO(os.path.join(HERE, "yolov8_custom.pt"))
        self.model.cpu()

    @bentoml.Runnable.method(batchable=False)
    def inference(self, input_img):
        result = self.model(input_img, verbose=False)[0]
        # every box, and [] when nothing is detected
        return json.loads(result.to_json())

    @bentoml.Runnable.method(batchable=False)
    def render(self, input_img):
        result = self.model(input_img, verbose=False)[0]
        # draw in memory instead of saving predictN/ folders on every request.
        # The runner is another process, so the image needs a format to be sent back.
        buf = io.BytesIO()
        PIL.Image.fromarray(result.plot()[..., ::-1]).save(buf, format="JPEG")
        buf.seek(0)
        return PIL.Image.open(buf)


yolo_v8_runner = bentoml.Runner(YOLOv8Runnable, name="yolov8_runnable")
svc = bentoml.Service("yolo_v8", runners=[yolo_v8_runner])


def check(img: PIL.Image.Image, ctx: bentoml.Context) -> PIL.Image.Image:
    if img.width * img.height > MAX_PIXELS:
        raise BadInput(f"image too large: {img.width}x{img.height}")
    ctx.response.headers["x-model-version"] = MODEL_LABEL
    return img.convert("RGB")


@svc.api(input=Image(), output=JSON())
async def invocation(input_img, ctx: bentoml.Context):
    return await yolo_v8_runner.inference.async_run([check(input_img, ctx)])


@svc.api(input=Image(), output=Image())
async def render(input_img, ctx: bentoml.Context):
    return await yolo_v8_runner.render.async_run([check(input_img, ctx)])
```

`render`가 `PIL.Image.fromarray(...)`를 그대로 돌려주면 `ValueError: unknown file extension`으로 500이 난다. Runner가 결과를 API 서버로 보내려고 이미지를 직렬화할 때 `image.format`을 쓰는데, 메모리에서 만든 이미지에는 그 값이 없다. JPEG로 한 번 인코딩해 다시 연 이미지를 돌려주면 형식이 붙는다.

### B-4. 응답, 상태 경로, 지연 확인 {#ch10-b-4}

1. 고친 서비스를 띄운다. 이번에는 API 서버를 둘만 띄운다.
   ```powershell
   cd ch10\yolo-fixed
   ..\..\.venv-ch10-yolo\Scripts\bentoml.exe serve service.py:svc --port 3011 --api-workers 2
   ```
2. 다른 터미널에서 시작 직후부터 `/livez`와 `/readyz`를 0.3초 간격으로 확인하면, 한동안 연결 거부(`000`)였다가 두 경로가 함께 200이 된다.
   ```text
     0.3s livez=000 readyz=000
    30.2s livez=200 readyz=200
   ```
   다른 작업이 함께 돌던 이번 측정은 30.2초였고, 한가할 때는 10초 남짓이었다.
3. Swagger에서 B-2와 같이 `two_cards.jpg`를 보낸다. 박스 두 개와 `x-model-version: ch08-id-card-detector/1` 헤더가 온다. 아래 화면은 C-2에서 같은 코드를 Bento 태그로 띄운 뒤 찍은 것이다.

   ![고친 서비스의 /invocation 응답. 박스 두 개와 x-model-version 헤더.](/images/ml-platform-engineering/sop/ch10-b-fixed-invocation.png)

   `/render`의 결과 이미지는 아래와 같다. 오른쪽 카드는 신뢰도 0.29로, 기본 신뢰도 문턱(0.25)을 겨우 넘었다.

   ![고친 서비스의 /render 결과. 두 카드에 id_card 0.79와 0.29 박스가 그려져 있다.](/images/ml-platform-engineering/sop/ch10-b-render-output.png)

4. 잘못된 입력을 보낸다.
   ```powershell
   curl.exe -s -w " [%{http_code}]`n" -X POST -H "Content-Type: image/jpeg" --data-binary "@ch08\samples\neg01.jpg" http://127.0.0.1:3011/invocation
   curl.exe -s -w " [%{http_code}]`n" -X POST -H "Content-Type: image/png" --data-binary "@ch10\huge.png" http://127.0.0.1:3011/invocation
   curl.exe -s -w " [%{http_code}]`n" -X POST -H "Content-Type: image/jpeg" --data "not an image" http://127.0.0.1:3011/invocation
   ```
   ```text
   [] [200]
   "BentoService error handling API request: image too large: 5000x4000" [400]
   "BentoService error handling API request: Failed to parse uploaded image file: cannot identify image file <_io.BytesIO object at 0x...>" [400]
   ```
5. Swagger 페이지 아래쪽의 **Infrastructure** 묶음이 책의 그림 10.7에 해당하는 상태 경로다.

   ![Swagger UI의 Service APIs와 Infrastructure 묶음. /invocation, /render와 /healthz, /livez, /readyz, /metrics.](/images/ml-platform-engineering/sop/ch10-b-endpoints.png)

6. 지연을 잰다. `ch10\loadtest.py`는 같은 이미지를 동시 요청 수를 바꿔 40건씩 보낸다.
   ```python
   import time, urllib.request, statistics, concurrent.futures as cf, sys
   data = open("ch10/two_cards.jpg", "rb").read()
   url = sys.argv[1]
   def call(_):
       t = time.perf_counter()
       req = urllib.request.Request(url, data=data, headers={"Content-Type": "image/jpeg"})
       urllib.request.urlopen(req).read()
       return (time.perf_counter() - t) * 1000
   for conc in (1, 4, 8):
       n = 40
       t0 = time.perf_counter()
       with cf.ThreadPoolExecutor(conc) as ex:
           lat = sorted(ex.map(call, range(n)))
       wall = time.perf_counter() - t0
       print(f"concurrency={conc:<2} n={n} p50={statistics.median(lat):6.1f}ms "
             f"p95={lat[int(n*0.95)-1]:6.1f}ms throughput={n/wall:5.1f} req/s")
   ```
   ```powershell
   .\.venv-ch10-yolo\Scripts\python.exe ch10\loadtest.py http://127.0.0.1:3011/invocation
   ```
   ```text
   concurrency=1  n=40 p50=  36.0ms p95=  50.8ms throughput= 25.9 req/s
   concurrency=4  n=40 p50=  64.3ms p95= 430.9ms throughput= 30.5 req/s
   concurrency=8  n=40 p50=  59.6ms p95=1149.4ms throughput= 33.1 req/s
   ```
   이 측정은 C-2에서 Bento 태그로 띄운 같은 서비스에 대한 것이다. 해석은 [배치와 지연](#batching-latency)에 적었다.

완료 기준: `two_cards.jpg`에 박스 두 개, `neg01.jpg`에 `[]`와 200, `huge.png`에 400이 오고, `ch10\yolo-fixed`에 `predict` 폴더가 생기지 않는다.

## C. Bento 빌드 {#ch10-c}

지금 위치는 전체 그림의 ③이다. 책 10.5를 따라간다.

### C-1. 저자 bentofile로 빌드 {#ch10-c-1}

```powershell
cd ch10\yolo-serving
..\..\.venv-ch10-yolo\Scripts\bentoml.exe build
```

```text
Using lowercased runnable class name 'yolov8runnable' for runner.
BentoML will not install Python to custom base images; ensure the base image 'ultralytics/ultralytics:8.0.203-cpu' has Python installed.
...
Successfully built Bento(tag="yolo_v8:rkfmjl63dcwtflaz").
```

경고가 말하듯 기반 이미지를 직접 지정하면 BentoML은 파이썬과 패키지를 그 이미지에 맡긴다. `bentoml-home\bentos\yolo_v8\rkfmjl63dcwtflaz\env\docker\Dockerfile`의 첫 줄은 `FROM ultralytics/ultralytics:8.0.203-cpu as base-container`이고, 설치하는 파이썬 패키지 목록 파일은 없다.

책의 1.1.6으로 빌드하면 같은 명령이 `Successfully built`를 출력하지만, 이어서 `bentoml list`와 `bentoml get`이 `KeyError: 'name'`으로 실패한다. 만들어진 `bento.yaml`에 `name`과 `version` 항목이 없다. 1.1.10으로 올려 다시 빌드하면 정상이다.

### C-2. 고친 bentofile로 빌드하고 태그로 실행 {#ch10-c-2}

1. `ch10\yolo-fixed\bentofile.yaml`을 만든다. 포함할 파일에 버전 정보를 넣고, 패키지를 고정하고, 라벨에 모델 버전을 적는다.
   ```yaml
   service: "service.py:svc"
   labels:
     owner: ch10
     model: ch08-id-card-detector
     model_version: "1"
   include:
     - "service.py"
     - "yolov8_custom.pt"
     - "model_info.json"
   python:
     packages:
       - ultralytics==8.3.40
       - torch==2.5.1
       - torchvision==0.20.1
       - numpy==1.26.4
       - opencv-python<4.12
     lock_packages: false
     extra_index_url:
       - https://download.pytorch.org/whl/cpu
   docker:
     python_version: "3.10"
     system_packages:
       - libgl1
       - libglib2.0-0
   ```
   `lock_packages: false`는 디스크 때문이다. 1.1의 기본값(true)은 빌드할 때 `pip-compile`로 의존성을 잠그는데, 이때 torch를 포함한 휠을 실제로 내려받는다. 실습 중 이 단계가 몇 분 동안 임시 폴더를 키워 중단했다. 버전을 모두 `==`로 적었으므로 잠그지 않아도 설치 결과의 차이는 하위 의존성에 한정된다.
2. 빌드하고 목록을 본다.
   ```powershell
   cd ch10\yolo-fixed
   ..\..\.venv-ch10-yolo\Scripts\bentoml.exe build
   ..\..\.venv-ch10-yolo\Scripts\bentoml.exe list
   ```
   ```text
   Successfully built Bento(tag="yolo_v8:rxu4w6w3dcwsplaz").

    Tag                       Size      Model Size  Creation Time
    yolo_v8:rxu4w6w3dcwsplaz  5.93 MiB  0.00 B      2026-11-08 11:03:13
    yolo_v8:rkfmjl63dcwtflaz  5.93 MiB  0.00 B      2026-11-08 11:03:07
   ```
   `Model Size`가 0인 것은 가중치가 BentoML 모델이 아니라 소스 파일로 들어갔기 때문이다. Bento 크기 5.93MiB의 대부분이 그 가중치다.
3. 소스 폴더가 아니라 태그로 띄운다. B-4의 응답과 지연 측정은 이렇게 띄운 서비스에서 했다.
   ```powershell
   ..\..\.venv-ch10-yolo\Scripts\bentoml.exe serve yolo_v8:rxu4w6w3dcwsplaz --port 3011 --api-workers 2
   curl.exe -s http://127.0.0.1:3011/metrics | Select-String 'request_total\{endpoint="/(invocation|render)'
   ```
   ```text
   bentoml_api_server_request_total{endpoint="/invocation",http_response_code="200",service_name="yolo_v8",service_version="rxu4w6w3dcwsplaz"} 2.0
   bentoml_api_server_request_total{endpoint="/render",http_response_code="200",service_name="yolo_v8",service_version="rxu4w6w3dcwsplaz"} 1.0
   bentoml_api_server_request_total{endpoint="/invocation",http_response_code="400",service_name="yolo_v8",service_version="rxu4w6w3dcwsplaz"} 1.0
   ```
   소스 폴더에서 띄웠을 때는 `service_version="not available"`이었다. 400 응답이 따로 집계되므로 클라이언트 오류와 서버 오류를 구분해 볼 수 있다.

### C-3. 컨테이너 이미지 {#ch10-c-3}

책은 `bentoml containerize yolo_v8:<태그>`와 `docker run --rm -p 3000:3000 yolo_v8:<태그>`로 이어진다. 이번 실습에서는 **실행하지 않았다.** 공유 PC의 디스크 여유가 실습 중 2~7GB 사이였는데, torch가 들어간 이미지를 빌드하면 Docker 디스크 파일이 수 GB 늘고 이 파일은 저절로 줄지 않는다. 디스크가 충분하다면 아래 명령으로 이어 가면 된다.

```powershell
..\..\.venv-ch10-yolo\Scripts\bentoml.exe containerize yolo_v8:rxu4w6w3dcwsplaz
docker run --rm -p 3000:3000 yolo_v8:rxu4w6w3dcwsplaz
docker image inspect yolo_v8:rxu4w6w3dcwsplaz --format "{{.Id}}"
```

마지막 명령의 값이 출시 기록에 들어갈 이미지 식별자다. 레지스트리에 올린 뒤에는 `docker image inspect --format "{{index .RepoDigests 0}}"`의 digest를 쓴다.

완료 기준: `bentoml list`에 두 Bento가 보이고, 태그로 띄운 서비스의 지표에 `service_version`이 Bento 버전으로 찍힌다.

## D. BentoML과 MLflow 추천 서비스 {#ch10-d}

지금 위치는 전체 그림의 ④~⑥이다. 책 10.6과 리스팅 10.1, 10.2를 따라간다.

### D-1. prod 별칭 준비 {#ch10-d-1}

리스팅 10.1은 `prod` 별칭을 찾는다. 그런데 9장 파이프라인은 `staging`만 만들었고, 9장의 등록 모델을 직접 바꾸면 9장의 기록이 흐려진다. 그래서 9장의 두 버전을 같은 원천을 가리키는 새 등록 모델 `ch10-recommender`로 복사하고 거기에 `prod`를 붙인다. 모델 파일은 복사되지 않고 같은 MLflow 모델(`models:/m-...`)을 가리킨다.

`ch10\register_recommender.py`:

```python
import os
os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://127.0.0.1:9000")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "minio")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minio123")
import mlflow
from mlflow import MlflowClient

mlflow.set_tracking_uri("http://127.0.0.1:5000")
c = MlflowClient()
src, name = "ch09-recommender", "ch10-recommender"
try:
    c.create_registered_model(name, description="ch10 serving lab: copies of ch09-recommender versions")
except Exception as e:
    print("exists:", type(e).__name__)
existing = {v.tags.get("copied_from") for v in c.search_model_versions(f"name='{name}'")}
for v in sorted(c.search_model_versions(f"name='{src}'"), key=lambda v: int(v.version)):
    tag = f"{src}/{v.version}"
    if tag not in existing:
        nv = c.create_model_version(name, source=v.source, run_id=v.run_id, tags={"copied_from": tag})
        print("created", nv.version, "from", tag, v.source)
c.set_registered_model_alias(name, "prod", "2")
```

```powershell
.\.venv-ch10-rec\Scripts\python.exe ch10\register_recommender.py
```

```text
created 1 from ch09-recommender/1 models:/m-3d3e5a3a2562492299e2e346c7383f14
created 2 from ch09-recommender/2 models:/m-4db3af9d5a1a4773a66d02e7f3c05a36
```

MLflow 화면의 **Models → ch10-recommender**에서 두 버전과 v2의 `@ prod`를 확인한다. 9장에서 본 대로 v2는 인기순 기준선보다 크게 낮은 모델이다. 여기서 `prod`는 서빙 실습을 위한 이름표이지 출시 판단이 아니다.

![MLflow의 ch10-recommender. Version 2에 prod 별칭, 두 버전 모두 copied_from 태그.](/images/ml-platform-engineering/sop/ch10-d-mlflow-recommender.png)

### D-2. 저자 서비스 실행 {#ch10-d-2}

1. 저자 폴더를 복사하고 실행을 막는 두 줄만 바꾼다. MLflow 주소와 모델 이름을 환경 변수로 받게 한다.
   ```powershell
   New-Item -ItemType Directory -Force ch10\rec-author | Out-Null
   Copy-Item upstream\ch10-movie-recommender\serving\* ch10\rec-author\
   ```
   `ch10\rec-author\service.py`에서 `import os`를 맨 위에 넣고 두 곳을 고친다.
   ```python
   def __init__(self, registered_model_name=os.environ.get("MODEL_NAME", "recommender_production"), device="cpu"):
       mlflow.set_tracking_uri(uri=os.environ["MLFLOW_TRACKING_URI"])
   ```
2. 환경 변수를 넣고 띄운다.
   ```powershell
   $env:MLFLOW_TRACKING_URI = "http://127.0.0.1:5000"
   $env:MLFLOW_S3_ENDPOINT_URL = "http://127.0.0.1:9000"
   $env:AWS_ACCESS_KEY_ID = "minio"; $env:AWS_SECRET_ACCESS_KEY = "minio123"
   $env:MODEL_NAME = "ch10-recommender"
   cd ch10\rec-author
   ..\..\.venv-ch10-rec\Scripts\bentoml.exe serve service:RecommenderRunable --port 3020
   ```
   ```text
   prometheus_client.registry.DuplicateTimeseries: Duplicated timeseries in CollectorRegistry: {'ranked_movie_present_counter', 'ranked_movie_present_counter_created', 'ranked_movie_present_counter_total'}
   ```
   `metrics.py`의 두 번째 카운터 `ranked_movie_absent_counter`도 `name="ranked_movie_present_counter"`로 등록돼 있다. 이름을 `ranked_movie_absent_counter`로 고치고 다시 띄우면 18초 뒤 준비된다. 로그에 `runs:/c1252d6c9f944228a7a93c26585708c4/model`이 찍혀 `prod`가 v2로 해석됐음을 알 수 있다.
3. 요청 본문을 파일로 만들어 보낸다. PowerShell에서 JSON 문자열을 직접 넘기면 따옴표가 깨지므로 파일이 안전하다.
   ```powershell
   New-Item -ItemType Directory -Force ch10\req | Out-Null
   '{"user_id": 50, "top_k": 5}' | Set-Content -NoNewline ch10\req\u50.json
   '{"user_id": 99999, "top_k": 5}' | Set-Content -NoNewline ch10\req\u99999.json
   '{"user_id": "abc"}' | Set-Content -NoNewline ch10\req\bad.json
   '{"user_id": 50, "top_k": 0}' | Set-Content -NoNewline ch10\req\k0.json
   foreach ($f in 'u50','u99999','bad','k0') {
     "$f -> " + (curl.exe -s -w "  [%{http_code}]" -X POST -H "Content-Type: application/json" --data-binary "@ch10\req\$f.json" http://127.0.0.1:3020/predict)
   }
   ```
   ```text
   u50 -> [132269, 123347, 54004, 89636, 89459]  [200]
   u99999 -> {"error":"An unexpected error has occurred, please check the server log."}  [500]
   bad -> {"error":"1 validation error for Input","detail":[{"type":"int_parsing","loc":["user_id"],"msg":"Input should be a valid integer, unable to parse string as an integer",...}]}  [400]
   k0 -> []  [200]
   ```
   상위 5개 중 54004(I Now Pronounce You Chuck and Larry)만 영화 목록에 있고 나머지 넷은 없는 ID다. 문자열 사용자 ID는 타입 힌트 덕분에 400이지만, 없는 사용자는 500이다.
4. 서버를 멈췄다가 다시 띄운 뒤 BentoML 모델 저장소를 본다.
   ```powershell
   ..\..\.venv-ch10-rec\Scripts\bentoml.exe models list
   ```
   ```text
    Tag                           Module          Size       Creation Time
    recommender:tte63hw3csmwtlaz  bentoml.mlflow  14.85 MiB  2026-11-08 10:35:00
    recommender:kbjzhn63cs65hlaz  bentoml.mlflow  14.85 MiB  2026-11-08 10:32:51
   ```
   시작할 때마다 같은 모델이 한 벌씩 늘어난다.

### D-3. 고친 서비스 {#ch10-d-3}

`ch10\rec-fixed\`에 D-2에서 고친 `metrics.py`를 복사하고 `service.py`를 새로 쓴다. 구조는 리스팅 10.1을 따른다. 다른 점은 클래스 이름을 `RecommenderService`로 바꾼 것, 그리고 Python 3.9에서는 `list[int] | None` 표기를 쓸 수 없어 `typing`의 `Optional[List[int]]`를 쓴 것뿐이다.

```python
import io
import os
from typing import List, Optional

import bentoml
import boto3
import mlflow
import numpy as np
import pandas as pd
import torch
from bentoml.exceptions import InvalidArgument
from mlflow import MlflowClient

from metrics import ranked_movie_absent_counter, ranked_movie_present_counter

MODEL_NAME = os.environ.get("MODEL_NAME", "ch10-recommender")
MODEL_ALIAS = os.environ.get("MODEL_ALIAS", "prod")
MODEL_VERSION = os.environ.get("MODEL_VERSION")  # pin a version for a release; alias otherwise
CATALOG_URI = os.environ.get(
    "CATALOG_URI", "s3://ch09-datasets/ml-latest-small/movies.parquet.gzip")
MAX_TOP_K = 100


@bentoml.service(
    resources={"cpu": "2"},
    traffic={"timeout": 10},
    workers=1,
)
class RecommenderService:
    def __init__(self) -> None:
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        client = MlflowClient()
        if MODEL_VERSION:
            mv = client.get_model_version(MODEL_NAME, MODEL_VERSION)
        else:
            mv = client.get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)
        # resolve the alias once and keep the concrete version for logs and headers
        self.model_label = f"{MODEL_NAME}/{mv.version}"
        print(f"loading {self.model_label} (alias={MODEL_ALIAS}, pinned={MODEL_VERSION}) run={mv.run_id}")
        self.model = mlflow.pytorch.load_model(f"models:/{MODEL_NAME}/{mv.version}", map_location="cpu")
        self.model.eval()
        self.n_users = self.model.user_factors.num_embeddings - 1
        bucket, key = CATALOG_URI[len("s3://"):].split("/", 1)
        body = boto3.client("s3", endpoint_url=os.environ["MLFLOW_S3_ENDPOINT_URL"]).get_object(Bucket=bucket, Key=key)["Body"].read()
        catalog = pd.read_parquet(io.BytesIO(body))
        # only real movie ids that the model has an embedding for
        ids = catalog.movieId.to_numpy()
        self.items = np.sort(ids[ids <= self.model.n_items])
        print(f"ready: users={self.n_users} catalog_items={len(self.items)}")

    @bentoml.api
    def predict(
        self,
        user_id: int,
        top_k: int = 10,
        ranked_movies: Optional[List[int]] = None,
        ctx: bentoml.Context = None,
    ) -> List[int]:
        if not 1 <= user_id <= self.n_users:
            raise InvalidArgument(f"unknown user_id {user_id}; valid range is 1..{self.n_users}")
        if not 1 <= top_k <= MAX_TOP_K:
            raise InvalidArgument(f"top_k must be between 1 and {MAX_TOP_K}")
        items = self.items
        if ranked_movies:
            ranked_movie_present_counter.inc()
            items = items[~np.isin(items, ranked_movies)]
        else:
            ranked_movie_absent_counter.inc()
        with torch.no_grad():
            # training used 0-based rows: userId - 1, movieId - 1
            users = torch.full((len(items),), user_id - 1, dtype=torch.long)
            scores = self.model(users, torch.as_tensor(items - 1, dtype=torch.long)).squeeze(1)
        top = torch.topk(scores, min(top_k, len(items))).indices.numpy()
        ctx.response.headers["x-model-version"] = self.model_label
        return items[top].tolist()
```

`workers=1`은 시작 비용 때문이다. 워커마다 MLflow에서 모델을 내려받고 카탈로그를 읽는다.

### D-4. 응답 확인 {#ch10-d-4}

1. D-2와 같은 환경 변수로 띄운다.
   ```powershell
   cd ch10\rec-fixed
   ..\..\.venv-ch10-rec\Scripts\bentoml.exe serve service:RecommenderService --port 3021
   ```
   ```text
   loading ch10-recommender/2 (alias=prod, pinned=None) run=c1252d6c9f944228a7a93c26585708c4
   ready: users=610 catalog_items=9742
   ```
2. http://127.0.0.1:3021 의 Swagger에서 **POST /predict**에 `{"user_id": 50, "top_k": 5}`를 보낸다. 모두 카탈로그에 있는 영화이고 응답 헤더에 해석된 버전이 있다.

   ![고친 추천 서비스의 /predict 응답. 3968, 2865, 2478, 45722, 7347과 x-model-version: ch10-recommender/2.](/images/ml-platform-engineering/sop/ch10-d-rec-predict.png)

   3968은 Bedazzled(2000), 45722는 Pirates of the Caribbean: Dead Man's Chest(2006)다. 학습과 같은 인덱스로 같은 모델을 직접 불러 계산한 상위 5개와 같았다.
3. 없는 사용자를 보내면 400과 이유가 온다.

   ![없는 user_id 99999에 대한 400 Bad Request와 valid range is 1..610 메시지.](/images/ml-platform-engineering/sop/ch10-d-rec-400.png)

   D-2의 나머지 요청도 보내면 `top_k: 0`은 `top_k must be between 1 and 100`과 400, `user_id: -3`도 400이다. 오류 본문이 `[{"error": ...}]`처럼 목록으로 감싸여 오는 것은 반환 타입을 `List[int]`로 선언한 1.4.40의 동작이다.

### D-5. Bento 빌드와 의존성 잠금 {#ch10-d-5}

1. `ch10\rec-fixed\bentofile.yaml`은 리스팅 10.2에 기반 이미지의 파이썬 버전과 기본 환경 변수를 더했다.
   ```yaml
   service: "service:RecommenderService"
   labels:
     owner: ch10
     stage: demo
   include:
     - "*.py"
   python:
     requirements_txt: "./requirements.txt"
   docker:
     python_version: "3.9"
   envs:
     - name: MODEL_NAME
       value: ch10-recommender
     - name: MODEL_ALIAS
       value: prod
   ```
2. 저자처럼 `requirements.txt`에 `torch`, `mlflow`만 적고 빌드하면 성공은 하지만, Bento의 `env\python\requirements.txt`에 잠긴 목록을 보면 CUDA 패키지가 들어 있다.
   ```powershell
   ..\..\.venv-ch10-rec\Scripts\bentoml.exe build
   Get-Content $env:BENTOML_HOME\bentos\recommender_service\<태그>\env\python\requirements.txt | Select-String '^(torch|nvidia|triton)'
   ```
   ```text
   nvidia-cublas-cu12==12.8.4.1
   nvidia-cudnn-cu12==9.10.2.21
   ...
   torch==2.8.0
   triton==3.4.0
   ```
   `nvidia-` 패키지가 15개였다. Windows에서 빌드해도 BentoML 1.4는 `x86_64-manylinux_2_36`용으로 잠그고, 그 플랫폼의 PyPI torch는 CUDA 빌드다.
3. CPU 휠 주소를 직접 적는다. `--extra-index-url`로 PyTorch 인덱스를 더하는 방법은 uv가 첫 번째로 찾은 인덱스의 버전만 보는 규칙 때문에 `certifi`를 찾지 못해 잠금에 실패했다.
   ```text
   bentoml==1.4.40
   torch @ https://download-r2.pytorch.org/whl/cpu/torch-2.8.0%2Bcpu-cp39-cp39-manylinux_2_28_x86_64.whl
   mlflow==3.0.0
   numpy==2.0.2
   pandas==2.3.3
   pyarrow
   boto3
   ```
4. 이번에는 `no wheels with a matching Python version tag (e.g., cp312)`로 실패했다. 빌드 환경의 파이썬(3.9)과 `docker.python_version`이 같으면 BentoML이 잠금 명령에 파이썬 버전을 넘기지 않고, uv가 PC의 다른 파이썬(3.12)을 기준으로 잡기 때문이다. `UV_PYTHON`을 지정하고 다시 빌드한다.
   ```powershell
   $env:UV_PYTHON = "3.9"
   ..\..\.venv-ch10-rec\Scripts\bentoml.exe build
   ```
   ```text
   Successfully built Bento(tag="recommender_service:5d2vlxw3cwf75laz").
   ```
   잠긴 목록에서 `nvidia-`로 시작하는 것은 BentoML의 의존성인 `nvidia-ml-py` 하나만 남았다. `bento.yaml`의 `models: []`가 보여 주듯 이 Bento에는 모델이 없다. 어떤 모델이 뜰지는 시작 시점의 `prod` 별칭이 정한다.

### D-6. 별칭을 옮기면 무엇이 바뀌는가 {#ch10-d-6}

롤백을 별칭 이동으로 할 수 있는지 확인한다. D-4의 서비스가 떠 있는 상태에서 진행한다.

```powershell
function Ask { $b = curl.exe -s -D ch10\hdr.txt -X POST -H "Content-Type: application/json" --data-binary "@ch10\req\u50.json" http://127.0.0.1:3021/predict; "$b  " + ((Get-Content ch10\hdr.txt | Select-String 'x-model-version') -join '') }
Ask
.\.venv-ch10-rec\Scripts\python.exe -c "import mlflow; from mlflow import MlflowClient; mlflow.set_tracking_uri('http://127.0.0.1:5000'); MlflowClient().set_registered_model_alias('ch10-recommender','prod','1')"
Ask
```

서비스 터미널에서 `Ctrl+C`로 멈추고 같은 명령으로 다시 띄운 뒤 한 번 더 `Ask`를 부른다. 세 번의 `Ask` 결과를 차례로 모으면 다음과 같다.

```text
1) 시작 직후:               [3968, 2865, 2478, 45722, 7347]  x-model-version: ch10-recommender/2
2) 별칭을 v1로 옮긴 뒤:      [3968, 2865, 2478, 45722, 7347]  x-model-version: ch10-recommender/2
3) 다시 시작한 뒤:           [115727, 103228, 122902, 59604, 63433]  x-model-version: ch10-recommender/1
```

별칭 이동만으로는 아무것도 바뀌지 않고, 재시작해야 반영된다. 3)의 목록은 9장 [F-3](../09-training-and-validation-2/#ch09-f-3)에서 v1로 계산한 사용자 50의 상위 5편과 같다. 확인이 끝나면 별칭을 v2로 되돌린다(마지막 명령의 `'1'`을 `'2'`로).

완료 기준: 고친 서비스가 카탈로그에 있는 영화만 돌려주고, 범위 밖 입력에 400을 돌려주며, 응답 헤더의 버전이 재시작 시점의 별칭과 일치한다.

## E. MLflow만으로 서빙 {#ch10-e}

지금 위치는 전체 그림의 ⑦이다. 책 10.7을 따라간다.

### E-1. 등록 모델을 그대로 서빙 {#ch10-e-1}

1. 책의 스크립트와 같이 별칭으로 서빙한다. 가상환경의 `Scripts`를 PATH 앞에 넣어야 한다. `mlflow models serve`는 내부에서 `uvicorn` 명령을 PATH에서 찾아 실행하는데, 이를 빼먹으면 PC에 설치된 다른 프로그램의 `uvicorn`이 잡혀 `returned non zero return code`로 실패한다.
   ```powershell
   $env:PATH = "$PWD\.venv-ch10-rec\Scripts;$env:PATH"
   mlflow models serve -m "models:/ch10-recommender@prod" --env-manager local -p 5010 -h 127.0.0.1
   ```
   `--env-manager local`은 모델의 `python_env.yaml`로 새 가상환경을 만들지 않고 현재 환경을 쓰라는 뜻이다. 현재 환경을 9장 학습과 같은 Python 3.9로 맞춰 두었기 때문에 쓸 수 있다.
2. 상태 경로는 정상이다.
   ```powershell
   curl.exe -s -w " [%{http_code}]`n" http://127.0.0.1:5010/ping
   curl.exe -s -w " [%{http_code}]`n" http://127.0.0.1:5010/version
   ```
   ```text
    [200]
   3.0.0 [200]
   ```
3. 예측은 어떤 형식으로도 되지 않는다. 등록된 서명은 `user`, `movie` 두 텐서다.

   ![MLflow의 ch10-recommender Version 2 스키마. 입력 user와 movie가 각각 Tensor int64.](/images/ml-platform-engineering/sop/ch10-e-mlflow-torch-schema.png)

   ```powershell
   '{"inputs": {"user": [49, 49, 49], "movie": [3967, 2864, 0]}}' | Set-Content -NoNewline ch10\req\mlflow-dict.json
   '{"inputs": [[49, 3967]]}' | Set-Content -NoNewline ch10\req\mlflow-list.json
   foreach ($f in 'mlflow-dict','mlflow-list') { curl.exe -s -w "  [%{http_code}]`n" -X POST -H "Content-Type: application/json" --data-binary "@ch10\req\$f.json" http://127.0.0.1:5010/invocations }
   ```
   ```text
   {"error_code": "BAD_REQUEST", ..., "stack_trace": "...TypeError: The PyTorch flavor does not support List or Dict input types. Please use a pandas.DataFrame or a numpy.ndarray\n"}  [400]
   {"error_code": "INVALID_PARAMETER_VALUE", "message": "... Model is missing inputs ['user', 'movie']."}  [400]
   ```
   `dataframe_split`으로 두 열을 보내도 첫 번째와 같은 `TypeError`였다. 첫 응답의 `stack_trace`에는 서버의 가상환경 경로가 그대로 들어 있었다.

### E-2. pyfunc 래퍼 모델 기록 {#ch10-e-2}

추천 절차를 MLflow 모델 안에 넣는다.

1. `ch10\mlflow-pyfunc\rec_pyfunc.py`:
   ```python
   import mlflow
   import numpy as np
   import pandas as pd
   import torch


   class RecommenderPyfunc(mlflow.pyfunc.PythonModel):
       """Wrap the two-input PyTorch model so MLflow serving takes user_id and top_k."""

       def load_context(self, context):
           self.model = mlflow.pytorch.load_model(context.artifacts["torch_model"], map_location="cpu")
           self.model.eval()
           self.n_users = self.model.user_factors.num_embeddings - 1
           ids = pd.read_parquet(context.artifacts["catalog"]).movieId.to_numpy()
           self.items = np.sort(ids[ids <= self.model.n_items])

       def predict(self, context, model_input: pd.DataFrame, params=None):
           out = []
           for user_id, top_k in zip(model_input["user_id"], model_input["top_k"]):
               if not 1 <= user_id <= self.n_users:
                   raise ValueError(f"unknown user_id {user_id}")
               with torch.no_grad():
                   users = torch.full((len(self.items),), int(user_id) - 1, dtype=torch.long)
                   scores = self.model(users, torch.as_tensor(self.items - 1, dtype=torch.long)).squeeze(1)
               out.append(self.items[torch.topk(scores, int(top_k)).indices.numpy()].tolist())
           return pd.DataFrame({"movie_ids": out})
   ```
2. `ch10\mlflow-pyfunc\log_pyfunc.py`는 현재 `prod` 버전과 카탈로그 파일을 아티팩트로 담아 새 모델을 기록하고 `ch10-recommender-pyfunc`로 등록한다.
   ```python
   import os, sys
   sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
   os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://127.0.0.1:9000")
   os.environ.setdefault("AWS_ACCESS_KEY_ID", "minio")
   os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minio123")
   import boto3
   import mlflow
   import pandas as pd
   from mlflow import MlflowClient
   from mlflow.models import infer_signature
   from rec_pyfunc import RecommenderPyfunc

   mlflow.set_tracking_uri("http://127.0.0.1:5000")
   mlflow.set_experiment("ch10-serving")
   client = MlflowClient()
   src = client.get_model_version_by_alias("ch10-recommender", "prod")
   here = os.path.dirname(os.path.abspath(__file__))
   catalog = os.path.join(here, "movies.parquet.gzip")
   boto3.client("s3", endpoint_url=os.environ["MLFLOW_S3_ENDPOINT_URL"]).download_file(
       "ch09-datasets", "ml-latest-small/movies.parquet.gzip", catalog)
   example = pd.DataFrame({"user_id": [50], "top_k": [5]})
   with mlflow.start_run(run_name="ch10-recommender-pyfunc") as run:
       mlflow.set_tags({"wraps": f"ch10-recommender/{src.version}", "wraps_run_id": src.run_id,
                        "catalog": "s3://ch09-datasets/ml-latest-small/movies.parquet.gzip"})
       info = mlflow.pyfunc.log_model(
           "model",
           python_model=RecommenderPyfunc(),
           artifacts={"torch_model": f"models:/ch10-recommender/{src.version}", "catalog": catalog},
           code_paths=[os.path.join(here, "rec_pyfunc.py")],
           signature=infer_signature(example, pd.DataFrame({"movie_ids": [[1, 2, 3, 4, 5]]})),
           input_example=example,
           registered_model_name="ch10-recommender-pyfunc",
       )
   latest = max(client.search_model_versions("name='ch10-recommender-pyfunc'"), key=lambda m: int(m.version))
   client.set_registered_model_alias("ch10-recommender-pyfunc", "prod", latest.version)
   print("run", run.info.run_id, "model", info.model_uri, "version", latest.version, "wraps", src.version)
   ```
3. 실행한다. 콘솔 인코딩이 cp949이면 MLflow가 마지막에 출력하는 이모지에서 `UnicodeEncodeError`가 나므로 `PYTHONIOENCODING`을 지정한다. 이 오류는 모델 등록이 끝난 뒤에 나기 때문에, 등록 모델 버전만 생기고 run은 `RUNNING`으로 남는다. 그렇게 됐다면 그 버전과 run을 지우고 다시 실행한다. 아래는 다시 실행한 결과다.
   ```powershell
   $env:PYTHONIOENCODING = "utf-8"
   .\.venv-ch10-rec\Scripts\python.exe ch10\mlflow-pyfunc\log_pyfunc.py
   ```
   ```text
   Created version '1' of model 'ch10-recommender-pyfunc'.
   run 1117db056b4e4897901c90403b894930 model models:/m-8231dc6309784bbf85978b8302e2d046 version 1 wraps 2
   ```
4. MLflow 화면의 **Models → ch10-recommender-pyfunc → Version 1**에서 `@ prod`와 새 스키마(`user_id`, `top_k` 입력, `movie_ids` 출력)를 확인한다.

   ![ch10-recommender-pyfunc Version 1. prod 별칭과 user_id, top_k 입력, movie_ids 출력 스키마.](/images/ml-platform-engineering/sop/ch10-e-mlflow-pyfunc.png)

### E-3. 래퍼 모델 서빙 {#ch10-e-3}

```powershell
mlflow models serve -m "models:/ch10-recommender-pyfunc@prod" --env-manager local -p 5010 -h 127.0.0.1
```

다른 터미널에서:

```powershell
'{"dataframe_records": [{"user_id": 50, "top_k": 5}]}' | Set-Content -NoNewline ch10\req\pyfunc.json
curl.exe -s -i -X POST -H "Content-Type: application/json" --data-binary "@ch10\req\pyfunc.json" http://127.0.0.1:5010/invocations
```

```text
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"predictions": [{"movie_ids": [3968, 2865, 2478, 45722, 7347]}]}
```

8초 만에 준비됐고, BentoML 서비스(D-4)와 같은 목록이다. 응답 헤더에는 어떤 버전이 답했는지가 없다. 없는 사용자를 보내면 400과 함께 서버 경로가 담긴 `stack_trace`가 온다.

완료 기준: `/invocations`가 D-4와 같은 추천 목록을 돌려준다.

## F. KServe 배포와 롤백 {#ch10-f}

지금 위치는 전체 그림의 ⑧~⑫다. 책 10.8의 KServe를 실제 클러스터에 설치하고, B-1의 탐지 모델을 `InferenceService`로 배포한다.

### F-1. KServe 설치(Standard 모드) {#ch10-f-1}

공식 설치 스크립트(`kserve-standard-mode-full-install-with-manifests.sh`)는 cert-manager를 Helm으로 새로 설치하고 Gateway API와 Envoy Gateway, LLM용 구성 요소까지 함께 넣는다. 6장에서 이미 cert-manager v1.13.3를 설치했고 Windows에서는 bash 스크립트를 그대로 쓸 수 없으므로, 릴리스의 매니페스트에서 InferenceService 컨트롤러에 필요한 것만 남겨 적용한다.

1. KServe v0.21.0의 매니페스트를 받는다.
   ```powershell
   New-Item -ItemType Directory -Force ch10\kserve | Out-Null
   curl.exe -L -o ch10\kserve\kserve.yaml https://github.com/kserve/kserve/releases/download/v0.21.0/kserve.yaml
   ```
2. `ch10\kserve\filter_kserve.py`로 LLM 서비스(`llmisvc`), 로컬 모델 캐시(`localmodel`), 커널 캐시(`kernelcache`) 구성 요소와 그 웹훅을 빼고, 기본 배포 모드를 Standard로, Ingress 생성은 끈다. CRD는 모두 남긴다.
   ```python
   import json, yaml
   docs = [d for d in yaml.safe_load_all(open("ch10/kserve/kserve.yaml", encoding="utf-8")) if d]
   skip = ("llmisvc", "localmodel", "kernelcache", "llminferenceservice")
   out = []
   for d in docs:
       name = d["metadata"]["name"]
       if d["kind"] != "CustomResourceDefinition" and any(s in name for s in skip):
           continue
       if d["kind"] in ("ValidatingWebhookConfiguration", "MutatingWebhookConfiguration"):
           d["webhooks"] = [w for w in d["webhooks"] if not any(
               s in w["name"] or s in w["clientConfig"].get("service", {}).get("name", "") for s in skip)]
       if d["kind"] == "ConfigMap" and name == "inferenceservice-config":
           deploy = json.loads(d["data"]["deploy"]); deploy["defaultDeploymentMode"] = "Standard"
           d["data"]["deploy"] = json.dumps(deploy, indent=2)
           ingress = json.loads(d["data"]["ingress"]); ingress["disableIngressCreation"] = True
           d["data"]["ingress"] = json.dumps(ingress, indent=2)
       out.append(d)
   yaml.safe_dump_all(out, open("ch10/kserve/ch10-kserve-core.yaml", "w", encoding="utf-8"), sort_keys=False)
   print("kept", len(out))
   ```
   ```powershell
   .\.venv-ch10-yolo\Scripts\python.exe ch10\kserve\filter_kserve.py
   ```
   `kept 43`이 나온다. 배포 3개와 데몬셋 2개 중 `kserve-controller-manager`만 남는다. 원본의 기본 모드는 `Serverless`라 그대로 쓰면 Knative가 없는 클러스터에서 InferenceService가 준비되지 않는다.
3. 네임스페이스를 만들고 적용한다. CRD가 큰 파일이라 `--server-side`로 적용한다.
   ```powershell
   kubectl create namespace kserve
   kubectl apply --server-side -f ch10\kserve\ch10-kserve-core.yaml
   ```
   처음 적용하면 마지막에 `no matches for kind "ClusterStorageContainer" in version "serving.kserve.io/v1alpha1"`가 난다. 같은 파일 안의 CRD가 아직 등록되기 전에 그 리소스를 만들려 해서다. 몇 초 뒤 같은 명령을 한 번 더 실행하면 오류 없이 끝난다.
4. 웹훅 인증서와 컨트롤러를 확인한다.
   ```powershell
   kubectl -n kserve get certificate,pods
   ```
   ```text
   NAME                                       READY   SECRET                       AGE
   certificate.cert-manager.io/serving-cert   True    kserve-webhook-server-cert   28s

   NAME                                             READY   STATUS    RESTARTS   AGE
   pod/kserve-controller-manager-688c888fd9-wjtdl   2/2     Running   0          3m14s
   ```
   cert-manager v1.13.3가 KServe의 웹훅 인증서를 발급했다. 컨트롤러 이미지(43.7MB)와 kube-rbac-proxy 이미지(31.1MB)를 받는 데 1분 남짓 걸렸다.

### F-2. 모델 위치와 접근 권한 {#ch10-f-2}

1. B-1의 가중치와 버전 정보를 버전 번호가 들어간 경로에 올린다. 경로가 곧 배포 명세에 적힐 모델 식별자가 된다.
   ```powershell
   .\.venv-ch10-yolo\Scripts\python.exe -c "import boto3; s3=boto3.client('s3', endpoint_url='http://127.0.0.1:9000', aws_access_key_id='minio', aws_secret_access_key='minio123'); 'ch10-models' in [b['Name'] for b in s3.list_buckets()['Buckets']] or s3.create_bucket(Bucket='ch10-models'); [s3.upload_file(f'ch10/yolo-fixed/{f}', 'ch10-models', f'detector/ch08-id-card-detector/1/{f}') for f in ('yolov8_custom.pt', 'model_info.json')]"
   ```
2. `ch10\kserve\ch10-setup.yaml`로 네임스페이스, S3 키를 담은 Secret, 그 Secret을 쓰는 ServiceAccount를 만든다. Secret의 주석이 storage-initializer에게 S3 주소와 HTTP 사용 여부를 알려 준다.
   ```yaml
   apiVersion: v1
   kind: Namespace
   metadata:
     name: ch10-serving
   ---
   apiVersion: v1
   kind: Secret
   metadata:
     name: ch10-s3
     namespace: ch10-serving
     annotations:
       serving.kserve.io/s3-endpoint: minio-service.kubeflow.svc.cluster.local:9000
       serving.kserve.io/s3-usehttps: "0"
       serving.kserve.io/s3-region: us-east-1
   type: Opaque
   stringData:
     AWS_ACCESS_KEY_ID: minio
     AWS_SECRET_ACCESS_KEY: minio123
   ---
   apiVersion: v1
   kind: ServiceAccount
   metadata:
     name: ch10-kserve-sa
     namespace: ch10-serving
   secrets:
     - name: ch10-s3
   ```
3. 예측 서버 코드 `ch10\kserve\detector_server.py`를 만든다. KServe V1 프로토콜의 모델 상태 경로와 예측 경로를 표준 라이브러리로 구현하고, 포트는 먼저 열되 모델을 읽고 한 번 예열한 뒤에야 준비 상태를 200으로 돌려준다.
   ```python
   """Minimal KServe V1 protocol server for the ch08 YOLO detector.

   KServe only needs a container that listens on a port. In practice you would
   build an image with the kserve SDK (kserve.Model); this lab uses the standard
   library so that the ultralytics image already on the kind node can run it.
   """
   import base64
   import io
   import json
   import os
   import threading
   from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

   from PIL import Image
   from ultralytics import YOLO

   MODEL_NAME = os.environ.get("MODEL_NAME", "ch10-detector")
   MODEL_DIR = os.environ.get("MODEL_DIR", "/mnt/models")
   PORT = int(os.environ.get("PORT", "8080"))
   MAX_PIXELS = 4096 * 4096

   state = {"ready": False, "model": None, "info": {}}
   lock = threading.Lock()


   def load():
       info = json.load(open(os.path.join(MODEL_DIR, "model_info.json")))
       model = YOLO(os.path.join(MODEL_DIR, "yolov8_custom.pt"))
       model(Image.new("RGB", (64, 64)), verbose=False)  # warm up before reporting ready
       state.update(model=model, info=info, ready=True)
       print(f"ready: {info['registered_model']}/{info['version']} sha256={info['sha256'][:12]}", flush=True)


   class Handler(BaseHTTPRequestHandler):
       def _send(self, code, body):
           data = json.dumps(body).encode()
           self.send_response(code)
           self.send_header("Content-Type", "application/json")
           info = state["info"]
           if info:
               self.send_header("x-model-version", f"{info['registered_model']}/{info['version']}")
           self.send_header("Content-Length", str(len(data)))
           self.end_headers()
           self.wfile.write(data)

       def do_GET(self):
           if self.path == "/":
               self._send(200, {"status": "alive"})
           elif self.path == f"/v1/models/{MODEL_NAME}":
               self._send(200 if state["ready"] else 503, {"name": MODEL_NAME, "ready": state["ready"]})
           else:
               self._send(404, {"error": "not found"})

       def do_POST(self):
           if self.path != f"/v1/models/{MODEL_NAME}:predict":
               return self._send(404, {"error": "not found"})
           if not state["ready"]:
               return self._send(503, {"error": "model not ready"})
           try:
               body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
               images = []
               for inst in body["instances"]:
                   img = Image.open(io.BytesIO(base64.b64decode(inst["image_b64"])))
                   if img.width * img.height > MAX_PIXELS:
                       raise ValueError(f"image too large: {img.width}x{img.height}")
                   images.append(img.convert("RGB"))
           except Exception as e:  # malformed JSON, base64 or image
               return self._send(400, {"error": f"bad request: {e}"})
           with lock:
               results = state["model"](images, verbose=False)
           self._send(200, {"predictions": [json.loads(r.to_json()) for r in results]})

       def log_message(self, fmt, *args):
           print(f"{self.address_string()} {fmt % args}", flush=True)


   if __name__ == "__main__":
       threading.Thread(target=load, daemon=True).start()
       ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
   ```
   PC에서 `MODEL_DIR=ch10\yolo-fixed`, `PORT=8090`으로 먼저 띄워 보면, 시작 직후 상태 경로는 연결되지 않다가 약 12초 뒤 `{"name": "ch10-detector", "ready": true}`가 된다.
4. 적용하고, 서버 코드를 ConfigMap으로 넣는다.
   ```powershell
   kubectl apply -f ch10\kserve\ch10-setup.yaml
   kubectl -n ch10-serving create configmap ch10-detector-server --from-file=ch10\kserve\detector_server.py --dry-run=client -o yaml | kubectl apply -f -
   ```

### F-3. InferenceService 적용 {#ch10-f-3}

1. `ch10\kserve\ch10-detector-isvc.yaml`. 이미지는 9장에서 kind 노드에 넣어 둔 `ultralytics/ultralytics:8.3.56-cpu`를 그대로 쓴다. `STORAGE_URI` 환경 변수가 storage-initializer를 붙이게 하는 신호다.
   ```yaml
   apiVersion: serving.kserve.io/v1beta1
   kind: InferenceService
   metadata:
     name: ch10-detector
     namespace: ch10-serving
     labels:
       release: ch10-detector-r1
   spec:
     predictor:
       serviceAccountName: ch10-kserve-sa
       minReplicas: 1
       maxReplicas: 1
       containers:
         - name: kserve-container
           image: ultralytics/ultralytics:8.3.56-cpu
           imagePullPolicy: IfNotPresent
           command: ["python3", "/app/detector_server.py"]
           env:
             - name: STORAGE_URI
               value: s3://ch10-models/detector/ch08-id-card-detector/1
             - name: MODEL_NAME
               value: ch10-detector
             - name: YOLO_CONFIG_DIR
               value: /tmp/yolo
           ports:
             - containerPort: 8080
               protocol: TCP
           readinessProbe:
             httpGet:
               path: /v1/models/ch10-detector
               port: 8080
             periodSeconds: 5
           livenessProbe:
             httpGet:
               path: /
               port: 8080
             initialDelaySeconds: 30
             periodSeconds: 10
           resources:
             requests: {cpu: 500m, memory: 1Gi}
             limits: {cpu: "2", memory: 2Gi}
           volumeMounts:
             - name: server-code
               mountPath: /app
       volumes:
         - name: server-code
           configMap:
             name: ch10-detector-server
   ```
   readiness는 모델 상태 경로를, liveness는 모델과 무관한 `/`를 본다. 모델을 읽는 동안 liveness가 실패해 재시작되는 일을 막기 위한 구분이다.
2. 적용하고 KServe가 만든 리소스를 본다.
   ```powershell
   kubectl apply -f ch10\kserve\ch10-detector-isvc.yaml
   kubectl -n ch10-serving get inferenceservice,deploy,svc,pods,hpa
   ```
   30초 뒤의 상태다. 초기화 컨테이너가 storage-initializer 이미지(약 92MB)를 받는 중이다.
   ```text
   NAME                                               URL                                             READY   ...   AGE
   inferenceservice.serving.kserve.io/ch10-detector   http://ch10-detector-ch10-serving.example.com   False         35s

   NAME                                      READY   UP-TO-DATE   AVAILABLE   AGE
   deployment.apps/ch10-detector-predictor   0/1     1            0           35s

   NAME                              TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
   service/ch10-detector-predictor   ClusterIP   10.96.113.37   <none>        80/TCP    35s

   NAME                                          READY   STATUS     RESTARTS   AGE
   pod/ch10-detector-predictor-b5dd9b8c5-phv9n   0/1     Init:0/1   0          35s

   NAME                                                          REFERENCE                            TARGETS              MINPODS   MAXPODS   REPLICAS
   horizontalpodautoscaler.autoscaling/ch10-detector-predictor   Deployment/ch10-detector-predictor   cpu: <unknown>/80%   1         1         1
   ```
   `InferenceService` 하나가 Deployment, Service, HPA로 바뀌었다. URL의 `example.com`은 Ingress 도메인의 기본값으로, Ingress를 만들지 않았으므로 실제로 열리지는 않는다.
3. 1분쯤 뒤 READY가 `True`가 된다. 초기화 컨테이너의 로그에서 모델 파일을 가져온 기록을 본다.
   ```powershell
   kubectl -n ch10-serving get inferenceservice
   kubectl -n ch10-serving logs deploy/ch10-detector-predictor -c storage-initializer --tail 3
   kubectl -n ch10-serving logs deploy/ch10-detector-predictor -c kserve-container --tail 3
   ```
   ```text
   NAME            URL                                             READY   ...   AGE
   ch10-detector   http://ch10-detector-ch10-serving.example.com   True          65s

   ... Downloaded object detector/ch08-id-card-detector/1/yolov8_custom.pt
   ... Successfully copied s3://ch10-models/detector/ch08-id-card-detector/1 to /mnt/models
   ... Model downloaded in 0.639153748001263 seconds.

   ready: ch08-id-card-detector/1 sha256=d8c5a0d2bf8f
   10.244.0.1 "GET /v1/models/ch10-detector HTTP/1.1" 200 -
   ```
   마지막 줄은 kubelet의 readiness 프로브다.

### F-4. 요청 보내기 {#ch10-f-4}

1. 세 번째 터미널에서 Service로 포트를 연결한다. 4장의 포트포워딩과 겹치지 않는 8095를 쓴다.
   ```powershell
   kubectl -n ch10-serving port-forward svc/ch10-detector-predictor 8095:80
   ```
2. 이미지를 base64로 바꿔 V1 형식으로 보낸다.
   ```powershell
   $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$PWD\ch10\two_cards.jpg"))
   "{`"instances`": [{`"image_b64`": `"$b64`"}]}" | Set-Content -NoNewline ch10\req\ks-two.json
   curl.exe -s -w " [%{http_code}]`n" http://127.0.0.1:8095/v1/models/ch10-detector
   curl.exe -s -i -X POST -H "Content-Type: application/json" --data-binary "@ch10\req\ks-two.json" http://127.0.0.1:8095/v1/models/ch10-detector:predict
   ```
   ```text
   {"name": "ch10-detector", "ready": true} [200]
   HTTP/1.0 200 OK
   Server: BaseHTTP/0.6 Python/3.11.10
   Content-Type: application/json
   x-model-version: ch08-id-card-detector/1

   {"predictions": [[{"name": "id_card", "class": 0, "confidence": 0.78848, "box": {"x1": 202.49304, "y1": 120.56191, "x2": 390.21524, "y2": 253.98024}}, {"name": "id_card", "class": 0, "confidence": 0.29102, "box": {"x1": 640.8335, "y1": 179.59755, "x2": 800.40088, "y2": 282.21329}}]]}
   ```
   B-4의 BentoML 서비스와 같은 박스 두 개다. 좌표의 마지막 자리가 조금 다른 것은 ultralytics 버전(8.3.40과 8.3.56)과 파이썬 버전(3.10과 3.11)이 다르기 때문이다.
3. 이미지가 아닌 값을 보내면 400이다.
   ```text
   {"error": "bad request: cannot identify image file <_io.BytesIO object at 0x75ece3b73420>"} [400]
   ```

### F-5. 책의 예시 명세 {#ch10-f-5}

책의 `InferenceService`를 이름과 네임스페이스만 바꿔 적용한다.

```yaml
apiVersion: "serving.kserve.io/v1beta1"
kind: "InferenceService"
metadata:
  name: "ch10-book-sample"
  namespace: ch10-serving
spec:
  predictor:
    model:
      modelFormat:
        name: sklearn
      storageUri: "gs://yolov8/models/pytorch/1.0/model"
```

```powershell
kubectl apply -f ch10\kserve\ch10-book-sample.yaml
kubectl -n ch10-serving get inferenceservice
kubectl -n ch10-serving describe inferenceservice ch10-book-sample
```

```text
NAME               URL                                             READY     ...
ch10-book-sample                                                   Unknown
ch10-detector      http://ch10-detector-ch10-serving.example.com   True

  Warning  InternalError  9s (x13 over 37s)  v1beta1Controllers  no runtime found to support predictor with model type: {sklearn <nil>}
```

상태의 `modelStatus`에는 `NoSupportingRuntime`, `transitionStatus: InvalidSpec`이 남는다. 이번 설치에는 `ClusterServingRuntime`을 넣지 않았으므로 sklearn 런타임도 없다. 런타임을 설치해도 이 명세는 YOLO PyTorch 모델을 scikit-learn 서버에 넘기는 셈이라 동작하지 않는다. 확인했으면 지운다.

```powershell
kubectl -n ch10-serving delete inferenceservice ch10-book-sample
```

### F-6. 잘못된 릴리스와 롤백 {#ch10-f-6}

1. 저장 위치를 존재하지 않는 버전 2로 바꾼 명세를 만든다. 실수로 아직 올리지 않은 모델 경로를 배포한 상황이다.
   ```powershell
   (Get-Content ch10\kserve\ch10-detector-isvc.yaml -Raw).Replace('ch10-detector-r1','ch10-detector-r2').Replace('ch08-id-card-detector/1','ch08-id-card-detector/2') | Set-Content ch10\kserve\ch10-detector-isvc-r2.yaml
   kubectl apply -f ch10\kserve\ch10-detector-isvc-r2.yaml
   ```
2. 1분 뒤 상태를 본다.
   ```powershell
   kubectl -n ch10-serving get inferenceservice,pods
   kubectl -n ch10-serving rollout status deploy/ch10-detector-predictor --timeout=10s
   ```
   ```text
   NAME                                               URL                                             READY   ...
   inferenceservice.serving.kserve.io/ch10-detector   http://ch10-detector-ch10-serving.example.com   True

   NAME                                           READY   STATUS                  RESTARTS     AGE
   pod/ch10-detector-predictor-68b4746cdb-lzjbq   0/1     Init:CrashLoopBackOff   3 (8s ago)   53s
   pod/ch10-detector-predictor-b5dd9b8c5-phv9n    1/1     Running                 0            2m39s

   Waiting for deployment "ch10-detector-predictor" rollout to finish: 1 old replicas are pending termination...
   error: timed out waiting for the condition
   ```
   새 Pod의 storage-initializer 로그는 `Storage initialization failed: Failed to fetch model. No model found in detector/ch08-id-card-detector/2.`다. 그 사이 F-4의 요청을 다시 보내면 여전히 200과 `x-model-version: ch08-id-card-detector/1`이 온다. READY가 `True`인 것은 기존 Pod가 살아 있어서이고, 새 릴리스가 반영됐다는 뜻이 아니다.
3. 이전 명세를 다시 적용해 되돌린다.
   ```powershell
   kubectl apply -f ch10\kserve\ch10-detector-isvc.yaml
   kubectl -n ch10-serving rollout status deploy/ch10-detector-predictor --timeout=60s
   kubectl -n ch10-serving get rs -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas,REVISION:.metadata.annotations.deployment\.kubernetes\.io/revision
   ```
   ```text
   deployment "ch10-detector-predictor" successfully rolled out
   NAME                                 DESIRED   READY    REVISION
   ch10-detector-predictor-68b4746cdb   0         <none>   2
   ch10-detector-predictor-b5dd9b8c5    1         1        3
   ```
   r1과 같은 Pod 템플릿이라 Deployment는 처음 ReplicaSet(`b5dd9b8c5`)을 리비전 3으로 다시 쓰고, 실패한 ReplicaSet은 0으로 줄였다. 응답하던 Pod는 한 번도 내려가지 않았다.

### F-7. 출시 기록 만들기 {#ch10-f-7}

`ch10\release_manifest.py`는 `InferenceService` 명세, 실행 중인 Pod의 이미지 ID, ConfigMap의 서버 코드 해시, MLflow 모델 버전을 모아 기록을 만든다.

```python
import hashlib, json, os, subprocess, sys
import yaml
import mlflow
from mlflow import MlflowClient

ns, name, release_id, previous = sys.argv[1:5]

def kubectl(*args):
    return json.loads(subprocess.check_output(["kubectl", "-n", ns, *args, "-o", "json"]))

isvc = kubectl("get", "inferenceservice", name)
c = isvc["spec"]["predictor"]["containers"][0]
env = {e["name"]: e["value"] for e in c.get("env", [])}
pods = kubectl("get", "pods", "-l", f"serving.kserve.io/inferenceservice={name}")["items"]
image_ids = sorted({s["imageID"] for p in pods for s in p["status"].get("containerStatuses", [])})
cm = kubectl("get", "configmap", "ch10-detector-server")
code_sha = hashlib.sha256(cm["data"]["detector_server.py"].encode()).hexdigest()

storage = env["STORAGE_URI"]  # s3://ch10-models/detector/<registered model>/<version>
registered, version = storage.rstrip("/").split("/")[-2:]
mlflow.set_tracking_uri("http://127.0.0.1:5000")
mv = MlflowClient().get_model_version(registered, version)
info = json.load(open(os.path.join("ch10", "yolo-fixed", "model_info.json")))

record = {
    "release_id": release_id,
    "previous_release_id": previous,
    "inference_service": f"{ns}/{name}",
    "isvc_generation": isvc["metadata"]["generation"],
    "image": c["image"],
    "image_id": image_ids,
    "server_code_sha256": code_sha,
    "storage_uri": storage,
    "model": {"registry_name": registered, "version": mv.version, "run_id": mv.run_id,
              "weights_sha256": info["sha256"],
              "release_decision": mv.tags.get("release_decision")},
    "api_contract": "KServe V1 /v1/models/ch10-detector:predict, instances[].image_b64",
    "ready": [f"{x['type']}={x['status']}" for x in isvc["status"]["conditions"]],
}
print(yaml.safe_dump(record, sort_keys=False, allow_unicode=True))
```

```powershell
.\.venv-ch10-yolo\Scripts\python.exe ch10\release_manifest.py ch10-serving ch10-detector ch10-detector-r1 none
```

출력은 [출시 정보와 롤백 단위](#release-and-rollback)에 실은 YAML이다. 롤백 뒤에 만들었으므로 `isvc_generation`이 3(r1, r2, r1 재적용)이다. 이 기록을 릴리스마다 남겨 두면 F-6의 롤백은 "기록의 r1 값으로 명세를 다시 적용한다"는 한 줄이 된다.

완료 기준: `kubectl -n ch10-serving get inferenceservice ch10-detector`가 `True`이고, 예측 응답의 `x-model-version`과 출시 기록의 모델 버전이 같다.

## G. 문제 해결과 정리 {#ch10-g}

### G-1. 자주 만나는 실패 {#ch10-g-1}

| 증상 | 위치 | 원인과 조치 |
| --- | --- | --- |
| `bentoml list`나 `bentoml serve <태그>`에서 `KeyError: 'name'` | C-1 | BentoML 1.1.6과 `cattrs 26`. 1.1.10으로 올린다 |
| `No module named 'pkg_resources'`, `containerize`의 `NotImplementedError` | A-3 | `setuptools<70`, `click==8.1.7` |
| `/invocation`이 박스를 하나만 돌려줌, 카드 없는 이미지에서 500 | B-2 | 저자 코드의 `results[0]`. B-3의 수정 |
| `/render`에서 `ValueError: unknown file extension` | B-3 | 메모리에서 만든 PIL 이미지에 형식이 없다. JPEG로 인코딩한 뒤 다시 연다 |
| 작업 폴더에 `predict`, `predict2`... | B-2 | 저자 코드의 `save=True`. B-3의 수정 |
| `DuplicateTimeseries` | D-2 | `metrics.py`의 카운터 이름 중복 |
| 존재하지 않는 영화 ID 추천, 학습 평가와 다른 목록 | D-2 | 인덱스 `- 1` 누락과 카탈로그 밖 후보. D-3의 수정 |
| `Registered model alias prod not found` | D-2 | 9장 파이프라인은 `staging`만 만든다. D-1 |
| `TypeError: code() argument 13 must be str, not int` | D-2, E-1 | 모델을 학습한 Python 3.9와 다른 버전에서 불러왔다 |
| Bento 잠금에 `nvidia-` 패키지 | D-5 | Linux PyPI torch는 CUDA 빌드. CPU 휠 주소를 적는다 |
| `Failed to lock PyPI packages`, `cp312` | D-5 | 잠금이 다른 파이썬을 잡았다. `$env:UV_PYTHON = "3.9"` |
| `Accessing hidden files is not allowed` | D-5 | BentoML 1.4는 경로에 `.`으로 시작하는 폴더가 있으면 빌드를 거부한다. 숨김 폴더 밖에서 빌드한다 |
| 별칭을 옮겼는데 응답 버전이 그대로 | D-6 | 별칭은 시작할 때 한 번 해석된다. 재시작한다 |
| `mlflow models serve`가 `non zero return code` | E-1 | 다른 `uvicorn`이 PATH에서 잡혔다. 가상환경의 `Scripts`를 PATH 앞에 둔다 |
| `The PyTorch flavor does not support List or Dict input types` | E-1 | 두 입력 모델은 PyTorch pyfunc로 서빙할 수 없다. E-2의 래퍼 |
| `UnicodeEncodeError: 'cp949' codec` | E-2 | MLflow의 이모지 출력. `$env:PYTHONIOENCODING = "utf-8"` |
| `no matches for kind "ClusterStorageContainer"` | F-1 | CRD 등록 전에 적용했다. 같은 명령을 다시 실행한다 |
| InferenceService가 계속 `False`이고 Knative 관련 오류 | F-1 | 기본 모드가 `Serverless`다. `defaultDeploymentMode`를 `Standard`로 |
| `no runtime found to support predictor` | F-5 | 지정한 형식의 `ClusterServingRuntime`이 없다 |
| 새 Pod가 `Init:CrashLoopBackOff`인데 READY는 `True` | F-6 | 저장 위치가 틀렸다. READY는 기존 Pod 기준이다. `rollout status`와 응답 헤더로 확인한다 |

이번 실행에서 실제로 만난 것은 `pkg_resources`, `NotImplementedError`, `Registered model alias prod not found`, `code() argument 13`, Knative 관련 오류를 뺀 나머지다. 빠진 다섯 가지는 6장과 9장에서 만났거나 설정을 미리 바꿔 피한 것이다.

### G-2. 정리 {#ch10-g-2}

1. 띄운 서버(`bentoml serve`, `mlflow models serve`, 포트포워딩)를 모두 `Ctrl+C`로 멈춘다.
2. KServe 배포와 실습 네임스페이스를 지운다. 네임스페이스를 지우면 InferenceService, Secret, ConfigMap이 함께 사라진다.
   ```powershell
   kubectl delete namespace ch10-serving
   ```
3. KServe 컨트롤러까지 지우려면 설치 파일로 지운다. 다른 장에서 KServe를 쓰지 않을 때만 한다. cert-manager는 6장의 것이므로 지우지 않는다.
   ```powershell
   kubectl delete -f ch10\kserve\ch10-kserve-core.yaml
   kubectl delete namespace kserve
   ```
4. MLflow의 `ch10-recommender`, `ch10-recommender-pyfunc` 등록 모델과 실험 `ch10-serving`, S3의 `ch10-models` 버킷은 11장에서 서빙 결과를 볼 때 쓸 수 있으므로 남겨 둔다. 지우려면 MLflow 화면에서 등록 모델과 실험을, 저장소 화면에서 버킷을 지운다. `ch10-recommender`의 버전은 9장 모델을 가리킬 뿐이라 지워도 9장의 파일은 남는다.
5. PC의 Bento와 모델 저장소는 `ch10\bentoml-home` 폴더를 지우면 함께 사라진다.

## 마치며 {#closing}

10장의 세 도구는 각자 다른 층을 맡는다. BentoML은 입력 검증과 전처리를 포함한 서비스 코드와 그 패키지를 맡는다. MLflow는 어떤 버전을 쓸지와 그 버전의 모델 파일을, KServe는 그 서비스를 클러스터에 몇 개, 어떤 자원과 프로브로 띄울지를 맡는다.

직접 돌려 보며 가장 크게 남은 것은 서빙에서 틀어지는 곳이 대부분 모델 바깥이었다는 점이다. 첫 박스만 돌려주는 인덱싱, 학습과 한 칸 어긋난 ID, 존재하지 않는 후보, 시작할 때 한 번만 읽히는 별칭, 기존 Pod 기준의 READY가 그랬다. 그래서 출시 기록에는 모델 버전과 함께 코드, 의존성, 이미지, 배포 명세를 남겨야 하고, 롤백은 그 묶음 전체를 되돌리는 일로 정의해야 한다. 다음 장은 이렇게 띄운 서비스가 실제로 받는 입력과 내놓는 예측을 관측하고 설명하는 문제로 넘어간다.

[이전: 09. 학습과 검증 II](../09-training-and-validation-2/), [시리즈 목차](../), [다음: 11. 모니터링과 설명가능성](../11-monitoring-and-explainability/)
