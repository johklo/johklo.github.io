---
title: "ML 플랫폼 실습 02. 합성 카드 탐지에서 기준선과 학습 모델 비교하기"
description: "02. 합성 카드 탐지에서 기준선과 학습 모델 비교하기 실행 절차, 결과 확인과 실패 실험"
date: 2026-10-24T15:00:00+09:00
lastmod: 2026-10-24T15:00:00+09:00
weight: 130
tags: ["ml-platform-labs", "mlops", "hands-on"]
aliases:
  - "/docs/tech/ml-platform-labs-02-cards/"
  - "/docs/tech/ml-platform-engineering-labs/ml-platform-labs-02-cards/"
---


합성 카드로 개인정보 없이 OCR이 아닌 객체 탐지를 익힌다.

## 데이터와 색상 기준선

```powershell
uv run ml-labs cards prepare --output data/cards --train 80 --validation 20 --test 20
uv run ml-labs cards train --data data/cards --output .ml-labs/runs/cards
uv run ml-labs cards evaluate --candidate .ml-labs/runs/cards/candidate.json --data data/cards --report .ml-labs/reports/cards.json --min-iou 0.75
uv run ml-labs register --candidate .ml-labs/runs/cards/candidate.json --report .ml-labs/reports/cards.json --name card-detector
```

`images/train`, `images/val`, `images/test`에는 PNG, 대응 `labels`에는 YOLO 텍스트가 있다. 각 줄은 클래스 번호와 중심 좌표, 폭, 높이이며 좌표는 이미지 크기로 정규화한다. 빈 라벨은 카드가 없는 예제다.

`color_component_baseline`은 반복 색으로 영역을 찾는 규칙 기준선이며 학습 모델이 아니다.

IoU는 정답, 예측의 교집합을 합집합으로 나눈다. 평균 IoU와 `box_recall_iou_0_5`는 카드 이미지에서, 음성 수와 오검출은 `negative_images`, `false_positives`로 기록한다. 단일 객체 지표는 표준 mAP와 다르다.

## 실제 YOLO 학습

```powershell
uv sync --locked --extra vision
uv run --extra vision ml-labs cards train --data data/cards --output .ml-labs/runs/cards-yolo --backend yolov8 --epochs 10
uv run --extra vision ml-labs cards evaluate --candidate .ml-labs/runs/cards-yolo/candidate.json --data data/cards --report .ml-labs/reports/cards-yolo.json --min-iou 0.5
```

Ultralytics는 첫 실행에 `yolov8n.pt`를 내려받을 수 있어 네트워크와 디스크가 필요하다. CPU 학습은 오래 걸리며 CLI에서 CPU를 명시한다.

`yolo/synthetic-cards/weights/best.pt`는 검증에서 고른 가중치다. 학습 로그를 확인하고, 완료 여부와 게이트 통과를 구분한다. 10 epoch와 임계치는 품질을 보장하지 않는다.

선택 테스트는 1 epoch CPU 학습과 MLflow 재로딩만 확인한다.

```powershell
$env:ML_LABS_RUN_VISION = "1"
uv run --extra dev --extra vision pytest -q tests/test_vision.py
Remove-Item Env:ML_LABS_RUN_VISION
```

설정, 가중치, 추론 코드와 Ultralytics 의존성을 MLflow에 저장한다. `candidate.json`에서 원천 run과 backend를 확인한다.

## 원격 추론의 입력 계약

로컬 경로는 원격 서버에서 유효하지 않을 수 있다. 모델은 `image_path` 또는 `image_base64` 하나만 받으며 AML MLflow 추론에는 이미지 바이트를 보낸다.

```powershell
$image = Get-ChildItem data/cards/images/test/*.png | Select-Object -First 1
$encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($image.FullName))
$request = @{ input_data = @{ columns = @("image_base64"); data = @(@($encoded)) } }
$request | ConvertTo-Json -Depth 8 | Set-Content .ml-labs/card-request.json
```

[Azure 과정](/docs/tech/ops/mlops/labs/ml-platform-labs-07-azure/)에서 관리형 endpoint 호출을 다룬다. 서버가 접근할 수 없는 PC 경로는 보내지 않는다.

## 게이트 거절과 합성 데이터의 한계

IoU 상한을 1보다 크게 두면 게이트 거절을 확인한다. 밝기, 회전, 가림 평가는 별도 데이터와 manifest가 필요하며, 변경 파일을 옛 manifest로 평가하면 지문 오류가 난다.

색상 기준선의 성능은 생성기 특성에 의존하며 실제 일반화를 뜻하지 않는다. 실데이터는 촬영 세션, 문서 단위로 분할하고 인접 동영상 프레임을 학습, 테스트에 나누지 않는다. 실제 신분증은 저장소에 추가하지 않는다.



[이전: 영화 추천](/docs/tech/ops/mlops/labs/ml-platform-labs-01-movies/) / [다음: Feast](/docs/tech/ops/mlops/labs/ml-platform-labs-03-feast/)


실행 코드는 [실습 저장소](https://github.com/johklo/ml-platform-engineering-labs)에서 내려받는다. [원본 가이드](https://github.com/johklo/ml-platform-engineering-labs/blob/main/docs/02-cards.md)
