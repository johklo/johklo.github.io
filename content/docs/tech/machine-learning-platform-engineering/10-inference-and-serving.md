---
title: "10. 모델 추론과 서빙"
description: "8장의 신분증 탐지 모델과 9장의 추천 모델을 BentoML, MLflow, KServe로 실제 API로 띄우며 서비스, 패키지, 이미지, 배포의 경계와 출시 정보, 롤백 단위를 확인하기"
date: 2026-10-18T21:30:00+09:00
lastmod: 2026-11-08T19:00:00+09:00
weight: 100
draft: false
tags: ["book-club", "ml-platform-engineering", "bentoml", "mlflow", "kserve", "model-serving"]
---

9장까지 남은 것은 파일이었다. 8장의 `best.pt`와 9장 MLflow에 등록된 추천 모델은 그 자체로는 요청을 하나도 받지 못한다. 10장은 입력을 검사하고, 학습 때와 같은 방식으로 바꾸고, 약속한 형식으로 답하는 서비스를 BentoML, MLflow, KServe로 만든다. 서빙에서 생긴 문제는 대부분 모델 바깥에서 나왔고, 그중 몇은 200 응답 뒤에 숨어 있었다.

## BentoML은 요청 처리와 모델 계산을 나눈다 {#bentoml-service-runner}

BentoML은 웹 서버, 입력 변환, Swagger 문서, 상태 확인 경로(`/livez`, `/readyz`), Prometheus 지표를 기본으로 준다. 모델 개발자는 어떤 입력을 받아 어떤 모델을 부르고 어떤 형식으로 돌려줄지만 쓰면 된다. 책이 쓰는 1.1은 HTTP 요청을 받는 Service(API 서버)와 모델을 올려 둔 Runner를 서로 다른 프로세스로 띄운다. 요청 처리는 가볍고 많으며 모델 계산은 무겁고 가속기를 독점하니, 둘을 따로 늘리려는 설계다. 대가는 직렬화다. 둘 사이를 오가는 이미지와 결과는 프로세스 경계를 넘어야 하고, 형식 정보가 없는 메모리 이미지는 넘기다 실패한다.

### 책의 BentoML 버전과 지금의 API {#bentoml-versions}

책 10.3~10.5의 탐지 서비스는 1.1.6의 `Runnable`, `Runner`, `bentoml.io`를 쓴다. 그런데 10.6의 리스팅 10.1(추천 서비스)은 1.2에서 들어온 `@bentoml.service` 클래스와 `@bentoml.api` 메서드를 쓴다. 클래스의 `__init__`이 Runner 생성자 역할을 하고, 입출력 형식은 타입 힌트로 정한다. 두 코드는 한 버전에서 함께 돌지 않아 탐지는 1.1 계열, 추천은 1.4로 따로 돌렸다. 1.4에서는 Runner와 `bentoml.io`가 사용 중단 경고를 내니 새로 시작한다면 클래스 방식이 기준이다. 1.1.6은 지금 설치하면 `cattrs`가 너무 새 버전으로 깔려 빌드한 Bento를 읽지 못하므로, 상한을 둔 1.1.10을 썼다.

### 배치와 지연 {#batching-latency}

`async`와 `await`는 API 서버가 Runner를 기다리는 동안 다른 요청을 받게 할 뿐 계산을 빠르게 하지 않는다. 저자 코드는 `batchable=False`라 Runner 하나가 이미지를 한 장씩 처리하고 나머지 요청은 줄을 선다. 동시 요청을 1개에서 8개로 늘리자 처리량은 초당 25.9건에서 33.1건으로 조금 늘었고, p95 지연은 51ms에서 1,149ms로 뛰었다.

책이 장점으로 드는 적응형 마이크로배칭은 이 대기를 묶음 처리로 바꾸는 장치다. 설정은 최대 묶음 크기와 최대 대기 시간 두 값이고, 처리량을 얻는 대신 먼저 온 요청이 기다린다. 용량을 넘는 요청은 시간 제한과 동시 요청 제한으로 빨리 실패시켜야 호출하는 쪽이 재시도나 대체 경로를 고를 수 있다.

## 200 응답이 계약을 지킨다는 보장은 없다 {#request-contract}

서비스의 API는 다른 팀과 맺은 계약이다. "이미지를 보내면 탐지된 신분증마다 클래스, 신뢰도, 박스를 돌려준다", "사용자 ID를 보내면 아직 안 본 영화를 점수 순으로 돌려준다" 같은 문장이 그 계약이고, 저자 코드는 정상 경로에서 200을 돌려주면서 이를 어긴다.

탐지 서비스는 결과를 한 번 더 인덱싱해 첫 박스만 돌려주고, 아무것도 못 찾으면 `IndexError`로 500을 낸다. "신분증이 없다"는 정상 답이 서버 오류로 집계된다. 추천 서비스의 문제는 더 조용하다. 학습은 `userId - 1`, `movieId - 1`을 임베딩 행으로 썼는데 서빙은 1을 빼지 않아, 다른 사용자의 임베딩으로 다른 영화의 점수를 매긴다. 후보도 1부터 최대 ID 193,609까지의 모든 정수라서 사용자 50의 상위 5개 중 4개가 카탈로그에 없는 영화였다. 학습과 서빙의 전처리가 어긋나는 training-serving skew다.

고친 탐지 서비스는 모든 박스를 돌려주고, 없으면 빈 목록을 준다. 고친 추천 서비스는 학습과 같은 인덱스와 카탈로그 후보를 쓰고, 범위 밖 사용자 ID나 `top_k`는 400으로 거절한다. 그 추천 목록이 9장 평가 스크립트의 목록과 같은지 맞춰 본 것이 단위 테스트보다 앞서야 할 계약 시험이었다. 타입 검사는 BentoML이 400으로 막아 주지만, 학습에 있던 사용자인지 같은 의미 검사는 서비스 코드가 해야 한다.

## 패키지와 별칭은 모델 버전을 저절로 고정하지 않는다 {#bento-and-image}

"모델을 배포했다"는 말에는 다섯 층이 섞여 있고, 층마다 버전을 가리키는 값이 다르다.

| 층 | 고정하는 것 | 식별자 |
| --- | --- | --- |
| 모델 아티팩트 | 가중치와 구조 | 레지스트리 버전, run_id, sha256 |
| 서비스 코드 | 입력 검증, 전처리, 응답 형식, 모델 로딩 방식 | 코드 커밋 |
| Bento | 코드, 포함 파일, 의존성 목록, 기반 이미지 지정 | Bento 태그 |
| 컨테이너 이미지 | 운영체제와 설치된 패키지 파일 | 이미지 digest |
| 배포 명세 | 복제 수, 자원, 프로브, 환경 변수, 저장 위치 | 리소스 명세와 generation |

Bento는 "이 코드를 이 의존성으로 실행하라"는 묶음이고, 모델이 들어 있는지는 서비스를 어떻게 썼느냐에 달렸다. 저자의 탐지 bentofile은 패키지 목록 없이 ultralytics 기반 이미지만 지정해, 실제 라이브러리 버전을 기반 이미지가 정했다. 추천 bentofile은 `torch`를 버전 없이 적어 Linux용 잠금에서 CUDA 패키지 15개가 따라왔다. 추천 Bento에는 모델이 아예 없다. 서비스가 시작할 때 MLflow의 `prod` 별칭을 읽어 모델을 내려받기 때문이다.

**별칭은 시작할 때 한 번만 해석된다.** 서비스가 v2로 떠 있는 동안 `prod`를 v1로 옮겨도 같은 프로세스는 계속 v2로 답했고, 재시작해야 v1이 떴다. 복제본이 서로 다른 시점에 재시작하면 버전이 섞일 수 있고, MLflow가 멈추면 새 Pod가 뜨지 못한다. 그래서 고친 서비스는 해석한 버전을 모든 응답의 `x-model-version` 헤더에 붙인다. `/metrics`에 붙는 `service_version`은 Bento 버전이고 모델 버전과는 다르다.

### 세 도구는 서로 다른 층을 맡는다 {#tool-boundaries}

책의 표 10.1은 KServe, BentoML, MLflow를 나란히 비교하지만, 직접 써 보면 셋은 경쟁하기보다 다른 층을 맡는다. BentoML은 전처리와 후처리를 담은 서비스 코드와 패키지를 맡는다. MLflow는 어느 버전을 쓸지와 모델 파일을, KServe는 그 서비스를 클러스터에 몇 개, 어떤 자원과 프로브로 띄울지를 맡는다.

`mlflow models serve`는 등록된 모델을 pyfunc 인터페이스 하나로 감싸 띄운다. 입력 하나에 예측 하나인 모델에는 충분하다. 하지만 9장 추천 모델처럼 `user`, `movie` 두 입력을 받는 PyTorch 모델은 어떤 형식으로 보내도 예측하지 못했다. 후보를 만들고 점수를 매겨 정렬하는 절차를 `PythonModel` 래퍼에 담아 다시 등록해야 했고, 응답 헤더나 400 오류 같은 HTTP 수준의 제어는 없다.

KServe에서는 `InferenceService` 하나를 선언하면 컨트롤러가 Deployment, Service, HPA를 만든다. Knative 기반 Serverless 모드는 0개 축소와 리비전별 트래픽 분할을 주고, Standard 모드는 Kubernetes 기본 리소스만 쓴다. 이번에는 Standard 모드를 썼다. 책의 예시는 YOLO 모델에 `sklearn` 런타임을 지정해 런타임을 찾지 못하고, 형식을 맞춰도 PyTorch 런타임은 TorchServe의 `.mar` 아카이브를 기대한다. 그래서 탐지 모델은 KServe V1 프로토콜을 따르는 사용자 정의 컨테이너로 올리고, `storage-initializer`가 S3의 가중치를 내려받게 했다.

## 출시 기록과 롤백은 묶음 단위다 {#release-and-rollback}

출시 기록은 지금 요청에 답한 것이 정확히 무엇인지 말해 줘야 한다. 앞의 다섯 층에 맞춰 클러스터와 MLflow에 직접 물어 만든 기록의 요지는 아래와 같다.

```yaml
release_id: ch10-detector-r1
isvc_generation: 3
image: ultralytics/ultralytics:8.3.56-cpu
storage_uri: s3://ch10-models/detector/ch08-id-card-detector/1
model:
  registry_name: ch08-id-card-detector
  version: '1'
  release_decision: hold
api_contract: KServe V1 /v1/models/ch10-detector:predict
```

`release_decision: hold`는 8장 수동 검토에서 흐린 사진과 작은 카드에 실패해 보류된 판단이 따라온 값이다. 서빙할 수 있다는 것과 출시해도 된다는 것은 다른 판단이고, 기록에 이 값이 없으면 보류된 모델이 서빙되고 있다는 사실이 묻힌다.

저장 위치를 존재하지 않는 버전으로 바꾼 명세를 적용하자 새 Pod는 `storage-initializer`에서 실패했다. 롤링 업데이트는 기존 Pod를 내리지 않아 요청은 계속 v1이 처리했고, 그동안 `kubectl get inferenceservice`는 내내 `READY True`였다. KServe의 Ready는 가용 복제본이 있다는 뜻이지 마지막 명세가 반영됐다는 뜻이 아니다. 반영 여부는 `rollout status`와 응답의 모델 버전으로 확인한다.

별칭으로 모델을 고르는 추천 서비스는 별칭을 옮기고 서비스를 재시작해야 롤백이 끝난다. 전처리를 고친 릴리스에서 코드만 저자 버전으로 되돌리면 다시 엉뚱한 영화를 추천한다. 모델, 전처리 코드, 의존성, 배포 명세를 한 단위로 기록하고 함께 되돌려야 하는 이유다.

## 책 본문과 저자 코드의 차이 {#book-vs-code}

10장 코드는 8~9장 저장소인 [object-detection-project](https://github.com/practical-mlops/object-detection-project)와 [movie-recommender-project](https://github.com/practical-mlops/movie-recommender-project)의 `serving` 폴더에 있다. 이해를 바꾸는 차이는 다음과 같다.

- 10.3은 BentoML 1.1.6, 리스팅 10.1은 1.2 이후 API라 두 코드가 한 환경에서 함께 돌지 않는다.
- 탐지 응답은 첫 박스만 담고, 추천은 학습과 한 칸 어긋난 인덱스로 카탈로그에 없는 ID까지 돌려준다.
- 추천 서비스는 MLflow 주소가 저자 환경의 IP로 박혀 있고, 같은 이름의 Prometheus 카운터 두 개 때문에 시작하자마자 죽는다.
- 서비스가 찾는 `prod` 별칭을 9장 파이프라인은 만들지 않는다. 9장은 `staging`만 남긴다.
- KServe 예시는 YOLO 모델에 `sklearn` 런타임을 지정한다.

## 실습 {#book-ch10-sop}

책 코드로 직접 실행한 순서와 결과 화면은 [10장 실습 기록](/docs/tech/machine-learning-platform-engineering/practice/ch10/)에 따로 모았다.

## 정리 {#closing}

서빙에서 틀어진 곳은 대부분 모델 바깥이었다. 첫 박스만 돌려주는 인덱싱, 학습과 한 칸 어긋난 ID, 시작할 때 한 번만 읽히는 별칭, 기존 Pod 기준의 READY가 모두 정상 응답 뒤에 있었다. 출시 기록에는 모델 버전과 함께 코드, 의존성, 이미지, 배포 명세를 남기고, 롤백은 그 묶음을 되돌리는 일로 정의한다. 응답 코드만으로는 모델이 맞게 답하는지 알 수 없고, 그 관측은 11장이 이어받는다.

[이전: 09. 학습과 검증 II](/docs/tech/machine-learning-platform-engineering/09-training-and-validation-2/), [시리즈 목차](/docs/tech/machine-learning-platform-engineering/), [다음: 11. 모니터링과 설명가능성](/docs/tech/machine-learning-platform-engineering/11-monitoring-and-explainability/)
