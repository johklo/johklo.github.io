---
title: "문서 파이프라인과 FAISS: 검색 가능한 정책 만들기"
description: "Bookway 정책의 수집, 분할, 임베딩, 색인 교체와 검색 평가"
date: 2026-10-25T08:43:00+09:00
weight: 10
tags: ["llmops", "rag", "faiss", "ingestion"]
---

안내서의 색인이 틀리면 설명을 잘하는 직원도 다른 쪽을 읽게 됩니다. FAISS는 벡터에서 가까운 후보를 찾는 검색 라이브러리입니다. 문서 수집, 원문 보관, 사용자 권한, HTTP 서비스, 백업까지 자동으로 제공하는 DB는 아닙니다.

## Bookway 정책을 색인하는 순서

```text
정책 원본 + 적용일 + 원문 ID
  → 허용된 원천 수집 / 파일 지문
  → 제목, 표, 예외를 보존한 텍스트 추출
  → 청크 + parent_id + 적용 범위
  → 고정 임베딩 모델, 차원, 정규화
  → FAISS 인덱스 + 별도 원문, 메타데이터 저장소
  → 평가 → policy-v3 / help-r8에 고정
```

반품 정책의 “7일”과 “전자책 제외”를 서로 관계없는 문서로 분리하면 숫자만 검색될 수 있습니다. 청크의 부모 절을 유지하고, 표는 행 값뿐 아니라 열 제목, 단위도 함께 저장합니다. PDF/HTML 파서는 문서 유형별로 검증하고, 이미지 스캔이면 OCR 단계와 오류율을 별도로 둡니다.

임베딩은 생성 모델과 다릅니다. Hugging Face 모델이나 관리형 embedding endpoint를 선택한 뒤 모델 revision, 차원, 정규화, 최대 길이를 manifest에 기록합니다. 재정렬 모델을 추가하면 그 revision과 후보 수, 지연도 평가합니다.

## 거리 계산의 최소 예제

`numpy`, `faiss-cpu` 환경에서 실행하는 합성 벡터 예제입니다. 실제 문장 임베딩이나 정책 답변 품질을 보여 주지는 않습니다.

```python
import faiss
import numpy as np

vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32")
query = np.array([[0.9, 0.1]], dtype="float32")
index = faiss.IndexFlatL2(2)
index.add(vectors)
distances, positions = index.search(query, 1)
source_ids = ["returns-v3#1", "shipping-v3#1"]
print(source_ids[int(positions[0][0])], float(distances[0][0]))
```

`IndexFlatL2`는 정확한 전수 검색이며 반환값은 **제곱 L2 거리**입니다. 인덱스 위치와 원문 ID의 대응을 같은 버전으로 보관해야 합니다. 벡터 파일만 새것이고 대응표가 옛것이면 다른 정책을 인용할 수 있습니다.

## 운영 저장소를 고르는 기준

단일 프로세스, 고정 문서, 작은 색인이라면 FAISS가 간단합니다. 동시 갱신, 서버 API, 필터, 복제가 필요하면 [Qdrant](../qdrant/), 관계형 데이터, 트랜잭션과 가까우면 [pgvector](../pgvector/)를 검토합니다. Chroma는 기존 [RAG 실습](../../ai-agents-and-applications/06-rag-fundamentals/)처럼 빠른 로컬 연결에도 쓸 수 있습니다.

FAISS에서 접근 불가 문서를 먼저 검색한 뒤 마지막에만 필터링하면 필요한 허용 문서를 놓칠 수 있습니다. 민감한 자료는 권한별 인덱스나 권한 필터가 있는 저장소 경로를 설계합니다. 서버가 인증 범위를 정하고 모델이 namespace를 선택하게 하지 않습니다.

## 교체와 삭제

새 색인을 별도 경로에 완성하고 문서 수, 지문, 검색 평가를 확인한 뒤 release 포인터를 바꿉니다. 라이브 파일을 제자리에서 덮어쓰지 않습니다. 임베딩 모델이 바뀌면 문서와 질문을 같은 공간으로 다시 계산합니다.

삭제, 정책 만료는 원문, 벡터, 부모, 캐시에 함께 반영합니다. 예전 release를 보존하더라도 폐기된 정책을 고객에게 계속 답하지 않도록 적용일과 서비스 정책을 분리합니다.

[FAISS 공식 시작 가이드](https://github.com/facebookresearch/faiss/wiki/Getting-started) / [검색 평가](../ragas/) / [LLMOps 전체 지도](../)
