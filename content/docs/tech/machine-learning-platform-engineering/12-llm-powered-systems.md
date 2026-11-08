---
title: "12. LLM 기반 시스템 설계"
description: "DakkaBot을 로컬 모델로 실제로 만들고, 검색과 문맥 구성과 생성을 나눠 Langfuse trace로 어디서 틀렸는지 구분하기"
date: 2026-10-18T21:30:00+09:00
lastmod: 2026-11-08T21:30:00+09:00
weight: 120
draft: true
tags: ["book-club", "ml-platform-engineering", "llmops", "rag", "langfuse", "chainlit"]
---

11장까지는 우리가 직접 학습한 모델 파일 하나가 예측을 결정했다. 모델을 바꾸면 결과가 바뀌고, 결과가 이상하면 학습 데이터와 학습 실행을 따라가면 됐다. 12장의 DakkaBot은 다르다. 모델은 남이 만든 LLM이고, 답변은 **어떤 문서를 어떻게 잘라 색인했는지, 질문으로 어떤 조각을 찾았는지, 그 조각을 어떤 지시와 함께 모델에 넣었는지, 모델이 그것을 얼마나 충실히 따랐는지**가 함께 정한다. 답이 틀렸을 때 "모델이 나쁘다"로 끝내면 고칠 곳을 찾을 수 없다.

그래서 이 장은 세 가지를 차례로 다룬다. 먼저 LLMOps가 기존 MLOps에서 무엇을 그대로 쓰고 무엇을 새로 관리해야 하는지 정리한다. 다음으로 RAG(Retrieval-Augmented Generation)를 검색, 문맥 구성, 생성으로 나눠 각 단계의 설계 선택이 왜 필요한지 설명한다. 마지막으로 Chainlit UI와 Langfuse 관측을 붙여, 한 번의 질문이 어떤 경로를 지나 어디에 기록되는지 확인한다. 이어지는 [실습 순서](#book-ch12-sop)에서는 저자 코드를 실제로 실행했다. 책은 Google Gemini API를 쓰지만, 이 실습은 비용과 API 키 없이 누구나 재현할 수 있도록 **Ollama의 로컬 모델로 바꿨고**, 나머지 구조(LangChain, FAISS, Chainlit, 자체 호스팅 Langfuse)는 책과 같다. 무엇을 왜 바꿨고 어떻게 되돌리는지는 [제공자 교체](#provider-swap)에 따로 적었다.

## 전체 그림 {#platform-map}

DakkaBot은 미리 하는 일(문서를 잘라 벡터로 바꾸고 인덱스로 저장)과 질문마다 하는 일(질문으로 조각을 찾아 모델에 넣고 답을 흘려보냄)로 나뉜다. 아래 그림은 이번 실습이 실제로 쓴 실행 위치와 전달물이다. 파란 상자가 이 장에서 만드는 부분, 회색이 앞 장에서 만든 플랫폼으로 실제 배포 때 다시 쓰는 부분, 점선 주황색이 13장에서 이어질 부분이다.

```mermaid
%%{init: {"flowchart": {"rankSpacing": 25, "nodeSpacing": 18, "padding": 6}}}%%
flowchart LR
    accTitle: 12장 실습에서 구성 요소가 주고받는 것
    accDescr: 개발자 PC의 index.py가 DATA 폴더의 Markdown 문서를 청크로 나눠 Ollama의 nomic-embed-text로 벡터를 만들고 FAISS 인덱스 파일로 저장한다. 브라우저의 질문은 Chainlit 서버의 DakkaBotCore로 들어가 질문 벡터로 FAISS에서 청크 다섯 개를 찾고, 지시와 청크와 질문을 Ollama의 llama3.2에 넣어 토큰을 받아 출처와 함께 브라우저로 흘려보낸다. 검색과 생성 기록은 Docker Compose로 띄운 Langfuse에 span으로 남고, 개발자는 Langfuse 화면에서 trace를 본다. 앞 장의 Kubernetes와 CI/CD는 배포할 때 재사용하고, 13장은 trace와 질문 집합으로 프롬프트 테스트, 가드레일, 비용 관리를 다룬다.
    subgraph PC["개발자 PC, Windows"]
        DOCS[("DATA/*.md<br/>DataKrypt 문서 5개")]
        IDX["index.py<br/>분할과 임베딩"]
        FAISS[("DATA/faiss_index<br/>index.faiss, index.pkl")]
        subgraph APP["Chainlit 서버 :8000"]
            UI["chainlit_app_streaming.py<br/>세션, 스트리밍, 출처"]
            CORE["DakkaBotCore<br/>검색, 문맥 구성, 생성"]
        end
        BR["브라우저"]
    end
    subgraph OLL["Ollama :11434"]
        EMB["nomic-embed-text<br/>768차원 임베딩"]
        LLM["llama3.2 3B<br/>답변 생성"]
    end
    subgraph LF["Docker Compose ch12-langfuse"]
        LFW["Langfuse web :3000<br/>worker"]
        LFS[("ClickHouse, Postgres<br/>Redis, MinIO")]
    end
    subgraph PREV["앞 장의 플랫폼"]
        K8S["Kubernetes, CI/CD<br/>MLflow, Prometheus"]
    end
    subgraph NEXT["13장"]
        GOV["프롬프트 테스트, 가드레일<br/>비용, 거버넌스"]
    end
    DOCS -->|"① Markdown 문서"| IDX
    IDX -->|"② 청크 345개, search_document:"| EMB
    IDX -->|"③ 벡터와 청크 원문"| FAISS
    BR -->|"④ 질문"| UI
    UI --> CORE
    CORE -->|"⑤ search_query: 질문"| EMB
    CORE -->|"⑤ 질문 벡터로 k=5 검색"| FAISS
    CORE -->|"⑥ 지시, 청크 5개, 질문"| LLM
    UI -->|"⑦ 답변 토큰, 출처 5개"| BR
    CORE -.->|"⑧ span, 토큰 수, 지연"| LFW
    LFW --> LFS
    LFW -->|"⑨ trace, 대시보드"| BR
    LFW -.->|"⑩ trace와 질문 집합"| GOV
    K8S -.->|"⑪ 이미지, 인덱스, 프롬프트 배포"| APP
    classDef thisch fill:#e8f1ff,stroke:#2f6fd6,stroke-width:2px;
    classDef prev fill:#f3f3f3,stroke:#999;
    classDef next fill:#fff6e5,stroke:#d08a00,stroke-dasharray:4 3;
    class DOCS,IDX,FAISS,UI,CORE,BR,EMB,LLM,LFW,LFS thisch;
    class K8S prev;
    class GOV next;
```

| 번호 | 누가 | 무엇을 넘기는가 | 어디에 남는가 | 실습 단계 |
| --- | --- | --- | --- | --- |
| ① | `index.py`의 `DirectoryLoader` | `DATA/` 아래 Markdown 문서 5개(`docs_1.md`~`docs_5.md`) | 메모리의 `Document` 목록, 경로가 `source` 메타데이터로 붙는다 | [C-1](#ch12-c-1) |
| ② | `index.py`가 Ollama 임베딩 호출 | 1,000자 단위로 자른 청크 345개, 앞에 `search_document:` | 768차원 벡터 | [C-1](#ch12-c-1) |
| ③ | `FAISS.from_documents`와 `save_local` | 벡터, 청크 원문, 메타데이터 | `DATA/faiss_index/index.faiss`, `index.pkl` | [C-1](#ch12-c-1) |
| ④ | 브라우저 | 질문 문자열 | Chainlit 세션(브라우저 화면의 대화 기록) | [E-2](#ch12-e-2) |
| ⑤ | `DakkaBotCore`의 retriever | `search_query:`를 붙인 질문 벡터, 가까운 청크 5개 | Langfuse의 `VectorStoreRetriever` span | [C-2](#ch12-c-2), [F-2](#ch12-f-2) |
| ⑥ | `DakkaBotCore`가 `ChatOllama` 호출 | 시스템 지시, 번호 붙인 청크 5개, 질문을 합친 프롬프트 | Langfuse의 `ChatOllama` generation(입력, 출력, 토큰 수) | [F-3](#ch12-f-3) |
| ⑦ | Chainlit | 토큰 스트림, 끝난 뒤 "Sources" 줄과 출처 패널 | 브라우저 화면 | [E-2](#ch12-e-2), [E-3](#ch12-e-3) |
| ⑧ | Langfuse Python SDK v3(OpenTelemetry) | span 트리, 지연, 토큰 사용량 | Langfuse의 ClickHouse | [F-1](#ch12-f-1) |
| ⑨ | Langfuse web | trace 목록, span 상세, 모델별 토큰과 비용 | 화면만, 데이터는 ClickHouse | [F-1](#ch12-f-1)~[F-4](#ch12-f-4) |
| ⑩ | 13장 | 실패 사례 trace와 평가 질문 집합 | 다음 장 | 이 장에서는 실행하지 않음 |
| ⑪ | 앞 장의 배포 경로 | 앱 이미지, 인덱스 파일, 프롬프트 버전 | 클러스터 | 이 장에서는 실행하지 않음 |

질문 하나가 실제로 지나가는 순서는 아래와 같다. 핵심은 **출처(검색 결과)가 답변 생성보다 먼저 정해진다**는 점이다. 답이 틀렸을 때 trace에서 검색 span의 출력부터 보면, 모델이 틀린 것인지 처음부터 잘못된 자료를 받은 것인지 나눌 수 있다.

```mermaid
sequenceDiagram
    accTitle: DakkaBot 질문 한 번의 처리 순서
    accDescr: 브라우저의 질문이 Chainlit을 거쳐 DakkaBotCore로 들어간다. DakkaBotCore는 Langfuse span을 열고 질문을 임베딩해 FAISS에서 청크 다섯 개를 찾아 출처를 먼저 화면에 알린다. 이어 프롬프트를 llama3.2에 보내 토큰을 하나씩 받아 화면에 흘려보내고, 끝나면 generation 기록과 span을 닫아 Langfuse로 보낸 뒤 완료 신호와 출처 목록을 보낸다.
    participant U as 브라우저
    participant C as Chainlit
    participant B as DakkaBotCore
    participant E as nomic-embed-text
    participant F as FAISS
    participant L as llama3.2
    participant T as Langfuse
    U->>C: 질문
    C->>B: process_query_stream(질문)
    B->>T: span dakkabot-query-stream 시작
    B->>E: "search_query: 질문"
    E-->>B: 768차원 벡터
    B->>F: 가장 가까운 5개
    F-->>B: 청크 5개와 source
    B-->>C: type sources, doc_count 5
    C-->>U: "Found 5 relevant documents"
    B->>L: 지시 + 청크 5개 + 질문
    loop 토큰마다
        L-->>B: 토큰
        B-->>C: type token
        C-->>U: 답변에 이어 붙이기
    end
    B->>T: generation(입력, 출력, 토큰 수), span 종료, flush
    B-->>C: type done
    C-->>U: Sources 줄과 출처 패널
```

## LLMOps: 그대로 쓰는 것과 새로 관리할 것 {#llmops-vs-mlops}

책은 LLMOps를 새 분야로 소개하지만 출발점은 "앞에서 만든 것을 버리지 않는다"는 말이다. DakkaBot도 결국 컨테이너로 묶어 Kubernetes에 올리고, CI/CD로 배포하고, Prometheus로 지연과 오류를 본다. 그림의 ⑪이 그 연결이다. 달라지는 것은 **무엇이 버전 관리 대상인가**와 **무엇으로 품질을 판단하는가**다.

| 질문 | 앞 장의 MLOps | DakkaBot의 LLMOps |
| --- | --- | --- |
| 결과를 정하는 것 | 학습한 모델 가중치 | 모델 제공자와 버전, 프롬프트, 검색 코퍼스와 인덱스, 검색 파라미터 |
| 바뀌면 재배포해야 하는 것 | 모델 파일, 전처리 코드 | 위 전부. 시스템 프롬프트 한 줄도 모델 교체만큼 결과를 바꾼다 |
| 품질 판단 | 정확도, RMSE 같은 정답 비교 | 의미가 맞는가, 근거와 일치하는가, 범위 밖 질문을 거절하는가 |
| 재현성 | 같은 입력이면 같은 예측 | temperature 0이어도 같은 답이 보장되지 않는다 |
| 비용 | 서버를 켜 둔 시간 | 요청마다 입력과 출력 토큰 수 |
| 디버깅 단위 | 요청 하나, 예측 하나 | 요청 하나 안의 여러 단계(검색, 문맥 구성, 생성) |

**샘플링 파라미터**가 재현성 문제의 출처다. LLM은 다음 토큰 후보의 확률 분포에서 하나를 고르는데, temperature는 분포를 얼마나 평평하게 만들지, top-k는 후보를 몇 개로 자를지, top-p는 누적 확률이 몇까지인 후보만 남길지를 정한다. 책은 사실 답변에는 temperature 0을 권하고 "완전히 결정적이지는 않다"고 덧붙인다. 이번 실습에서 실제로 그랬다. temperature 0, 같은 프롬프트(입력 665토큰)로 "What is the capital of Australia?"를 네 번 물었더니 세 번은 문서와 무관하다며 답하지 않았고, 한 번은 같은 말을 한 뒤 "Canberra"라고 답했다([E-3](#ch12-e-3)). 그래서 `assert answer == expected` 같은 테스트는 쓸 수 없고, 의미와 근거로 채점하는 평가가 필요하다. 이것이 13장의 출발점이다.

**토큰 예산**은 설계 제약이다. 입력(문맥 창)과 출력(`max_tokens`) 모두 한도가 있어서, 청크를 많이 넣으면 답할 자리가 줄고 비용과 지연이 늘어난다. 책의 예는 500토큰 청크 50개면 생성 전에 25,000토큰을 쓴다는 것이다. 이번 실습의 DakkaBot은 1,000자 청크 5개를 넣어 프롬프트가 1,244토큰이었다. 로컬 모델에는 한도가 하나 더 있다. Ollama는 `num_ctx`(문맥 길이)를 넘는 프롬프트를 오류 없이 앞부분부터 잘라 버리므로, 코드에서 8,192로 명시했다.

## 왜 RAG인가 {#why-rag}

사내 문서를 LLM으로 답하는 가장 단순한 방법은 문서 전체를 프롬프트에 넣는 것이다. 책은 이것이 안 되는 이유를 네 가지로 든다. 문서가 문맥 창보다 크고, 긴 프롬프트에서는 모델이 초점을 잃으며, 한 부분을 오해하면 답 전체가 무너지고, 질문마다 같은 문서를 다시 넣는 비용이 크다. RAG는 **찾는 일과 쓰는 일을 나눠서** 질문과 관련된 조각만 넣는다. 덕분에 모델을 다시 학습하지 않아도 문서가 바뀌면 인덱스만 다시 만들면 되고, 답에 근거 문서를 붙여 사람이 확인할 수 있다.

RAG와 파인튜닝은 목적이 다르다. RAG는 모델이 모르는 **지식을 외부에서 공급**하는 방법이고, 파인튜닝은 모델의 **행동, 형식, 특화 능력**을 바꾸는 방법이다. 사내 규정처럼 자주 바뀌고 출처가 중요한 지식은 RAG가 맞고, "항상 이 JSON 형식으로 답하라" 같은 행동은 프롬프트나 파인튜닝의 문제다. RAG도 잘못된 조각을 찾거나 조각을 잘못 읽으면 틀린 답을 낸다. 아래 설계 선택은 모두 그 두 실패를 줄이기 위한 것이다.

## 검색 설계 {#retrieval-design}

검색은 LLM이 무엇을 보게 될지 정한다. 검색이 틀리면 뒤에서 아무리 좋은 모델을 써도 근거 없는 답이 나온다.

### 청크 분할: 얼마나 잘라야 찾을 수 있는가 {#chunking}

문서를 통째로 임베딩하면 한 벡터에 여러 주제가 섞여 질문과 가까워지기 어렵고, 찾아도 너무 길어 프롬프트에 다 넣을 수 없다. 그래서 문서를 청크로 자른다. 저자 코드는 `RecursiveCharacterTextSplitter`로 `chunk_size=1000`, `chunk_overlap=200`, 구분자 `["\n## ", "\n### ", "\n\n", "\n", " ", ""]`를 쓴다. 제목에서 먼저 자르고, 안 되면 문단, 줄, 단어 순으로 내려가 1,000자 안에 맞추는 방식이다. 겹침(overlap)은 경계에서 잘린 문장이 양쪽 청크 어디에서도 의미를 잃지 않게 하는 장치다.

여기서 책 본문과 코드가 다르다. 책은 "200토큰 겹침"이라고 쓰지만 이 splitter는 **문자 수**를 센다. 1,000자는 영어 기준 대략 250토큰이다. 실제로 문서 5개는 청크 345개가 됐다. 잘린 결과를 보면 청크 경계가 의미 경계와 늘 맞지는 않는다. "How often should production API keys be rotated?"에 가장 가까운 청크는 사고 대응 절차의 "5. Post-Incident"로 시작하는 청크였는데, 그 뒤에 이어지는 키 교체 주기 표가 같은 청크에 들어 있었기 때문이다. 청크의 첫 줄만 보고 관련이 없다고 판단하면 안 되는 이유다.

### 임베딩: 문서와 질문을 같은 공간에 놓는다 {#embeddings}

임베딩 모델은 텍스트를 의미가 비슷하면 가까운 벡터로 바꾼다. "API credentials를 어떻게 바꾸나"와 "key rotation 절차"가 단어를 공유하지 않아도 가까워지는 것이 키워드 검색과의 차이다. 책의 `GeminiEmbeddings`는 문서에는 `task_type="RETRIEVAL_DOCUMENT"`, 질문에는 `RETRIEVAL_QUERY`를 붙인다. 문서와 질문은 길이와 문체가 달라서, 모델에 어느 쪽인지 알려 주면 검색이 좋아진다. 이번 실습의 `nomic-embed-text`도 같은 생각을 문자열 접두어로 구현한다. 문서는 `search_document: `, 질문은 `search_query: `를 앞에 붙인다.

임베딩 모델은 인덱스와 한 몸이다. 색인할 때와 검색할 때 다른 모델을 쓰면 두 벡터는 서로 다른 좌표계에 있다. 더 위험한 점은 **차원이 같으면 오류가 나지 않는다**는 것이다. `nomic-embed-text`와 책의 `text-embedding-004`는 둘 다 768차원이라, Gemini로 만든 인덱스를 nomic으로 검색해도 FAISS는 아무 경고 없이 엉뚱한 청크를 돌려준다. 그래서 인덱스는 임베딩 모델 이름과 함께 버전을 매기고, 모델을 바꾸면 새 인덱스를 따로 만들어 평가한 뒤 전환한다. 실습 코드에서는 `FAISS_INDEX_PATH`를 제공자마다 다르게 두는 것으로 이 규칙을 지킨다.

### 벡터 저장소: FAISS는 검색 엔진이지 데이터베이스가 아니다 {#vector-store}

FAISS는 수많은 벡터 중 가장 가까운 것을 빨리 찾는 라이브러리다. 저자 코드는 정확 검색(Flat) 인덱스를 쓰고, 거리는 L2다. 값이 작을수록 가깝다. FAISS 자체에는 권한, 부분 삭제, 백업, 동시 갱신 같은 데이터베이스 기능이 없다. 책이 운영 단계에서 Pinecone, Weaviate, Chroma 같은 벡터 DB를 언급하는 이유다.

저장 형식도 주의해야 한다. `save_local`은 벡터(`index.faiss`)와 청크 원문, 메타데이터(`index.pkl`)를 따로 쓰고, `index.pkl`은 Python pickle이다. 그래서 불러올 때 `allow_dangerous_deserialization=True`가 필요하다. pickle 파일은 불러오는 순간 코드를 실행할 수 있으므로, 인덱스 파일은 모델 파일과 같은 수준으로 출처와 무결성을 관리해야 한다. 인덱스 안에는 원문이 그대로 들어 있다는 점도 기억해야 한다. 원문이 민감하면 인덱스도 같은 등급의 데이터다.

### 검색 개수 k와 임계값 {#retrieval-k}

`as_retriever(search_kwargs={"k": 5})`는 무조건 가장 가까운 5개를 돌려준다. 적으면 필요한 근거를 놓치고, 많으면 잡음과 토큰 비용이 는다. 책은 "기본 3개 대신 5개"라고 설명하지만 LangChain 벡터 저장소 retriever의 기본값은 4개다.

더 중요한 것은 **임계값이 없다**는 점이다. 실습에서 거리를 직접 찍어 보면 차이가 분명하다.

| 질문 | 상위 5개 L2 거리 |
| --- | --- |
| How do I rotate encryption keys? | 0.558 ~ 0.648 |
| How often should production API keys be rotated? | 0.389 ~ 0.732 |
| What is the capital of Australia? | 0.936 ~ 0.998 |

문서와 무관한 질문도 5개를 받아 오고, UI는 그것을 "출처"로 보여 준다. 출처가 붙어 있다고 근거가 있는 것은 아니다. 이 코퍼스에서는 0.8 근처에 임계값을 두면 범위 밖 질문을 걸러낼 수 있어 보이지만, 그 값은 이 임베딩 모델과 이 문서에서만 의미가 있고 평가 질문 집합으로 정해야 한다. 이번 실습은 저자 코드대로 임계값 없이 두고, 그 결과를 [E-3](#ch12-e-3)에서 확인한다.

## 문맥 구성과 근거 표시 {#augmentation-grounding}

문맥 구성(augmentation)은 찾은 청크를 질문과 함께 하나의 프롬프트로 엮는 단계다. 저자 코드의 최소 버전(리스팅 12.10, 12.12)은 청크를 빈 줄로 이어 붙이고 "Context, Question, Answer" 틀에 넣는다. `DakkaBotCore`(리스팅 12.14)는 여기에 세 가지를 더한다. 청크마다 `**Document 1:**`처럼 번호를 붙이고, "DataKrypt 전문 개발자 도우미"라는 역할을 주며, "문서에 근거해 답하라, 모르면 모른다고 하라, DataKrypt 정보에 집중하라" 같은 지시를 넣는다.

이 단계에서 확인할 것은 세 가지다.

- **실제로 무엇이 들어갔는가**. 검색 결과와 프롬프트에 들어간 내용은 다를 수 있다. 길이 제한으로 잘리거나, 형식이 깨지거나, 다른 문서와 섞인다. 저자 코드의 프롬프트는 클래스 안에서 들여쓴 f-string이라 지시 줄마다 공백 12칸이 그대로 들어간다. Markdown에서 4칸 이상 들여쓴 줄은 코드 블록이 되므로, Langfuse 화면에서도 지시문이 코드 블록으로 보인다([F-3](#ch12-f-3)). 모델에 따라 지시를 덜 따르게 만들 수 있고 토큰도 낭비한다.
- **출처를 사용자가 볼 수 있는가**. 책은 출처 표시를 신뢰의 핵심으로 설명하고, `process_query_stream`도 출처를 가장 먼저 내보낸다. 그런데 저자의 Chainlit 앱은 그 출처를 변수에 받아 두기만 하고 화면에 그리지 않는다. 실습에서는 답변 끝에 "Sources" 줄과 청크 원문 패널을 붙였다([B-3](#ch12-b-3)).
- **출처가 곧 근거는 아니다**. 출처는 "이 청크들을 모델에 줬다"는 뜻이지 "답의 각 문장이 이 청크에 있다"는 뜻이 아니다. 문장 단위 근거 확인은 사람이 하거나 13장의 평가 도구가 한다.

검색된 문서는 지시가 아니다. 문서 안에 "이전 지시를 무시하라" 같은 문장이 있으면 모델은 그것을 지시로 읽을 수 있다(간접 프롬프트 주입). 문맥 구성 단계에서 문서와 지시를 구분해 표시하고, 사용자가 볼 권한이 있는 문서만 검색되도록 검색 단계에서 거르는 것이 기본이다. 생성 뒤 답변 문장을 검사하는 것으로 권한 필터를 대신할 수는 없다.

## 생성 {#generation}

생성 단계는 모델과 샘플링 설정, 출력 규칙을 정한다. 책은 `gemini-2.5-flash`를 `temperature=0`으로 쓰고, 이번 실습은 같은 자리에 Ollama의 `llama3.2`(3B 파라미터, 4비트 양자화, 2.0GB)를 같은 temperature로 넣었다.

모델 크기가 답의 질을 얼마나 바꾸는지는 같은 검색 결과로 모델만 바꿔 보면 드러난다. "How often should production API keys be rotated?"에 대해 두 로컬 모델은 같은 청크 5개를 받았다.

| 모델 | 걸린 시간(CPU) | 답 |
| --- | --- | --- |
| `llama3.2` 3B | 49.4초 | "every 90 days"라고 맞게 답하고 근거 표를 인용했다. 다만 뒤에 API 키 교체 명령과 암호화 키 교체 API를 섞은 예시를 덧붙였다 |
| `gemma3:270m` | 5.8초 | 질문과 무관한 사용자 활동 조회 API의 JSON 예시를 그대로 복사했다 |

검색은 둘 다 맞았다. 270M 모델은 문맥에서 답을 골라내는 능력 자체가 부족했고, 3B 모델은 답을 찾았지만 문맥의 인접 절차를 섞었다. 1~2B 모델(`llama3.2:1b`, `qwen2.5:1.5b` 등)은 디스크 여유가 없어 이번에 실행하지 않았지만, 크기로 보면 이 둘 사이에 있다. 사실 하나를 찾는 질문은 대체로 맞히지만, 여러 절차를 구분하거나 "모르면 모른다고 하라" 같은 지시를 끝까지 지키는 능력은 3B보다 더 떨어질 것으로 예상하고, 바꿔 쓴다면 같은 질문으로 직접 비교해 봐야 한다. Gemini 같은 대형 상용 모델은 이 차이가 훨씬 작고, 답도 몇 초 안에 나온다. 반대로 말하면, 작은 로컬 모델은 **검색이 맞고 생성이 틀린 사례**를 쉽게 보여 주기 때문에 실패를 나눠 보는 연습에는 오히려 좋다.

## 제공자 교체: Gemini 대신 Ollama {#provider-swap}

책은 Google AI Studio에서 API 키를 받아 Gemini로 임베딩과 생성을 한다. 이 실습은 두 가지 이유로 Ollama의 로컬 모델로 바꿨다. 첫째, 독자 누구나 비용과 계정 없이 같은 결과를 재현할 수 있어야 한다. 둘째, 책의 모델이 지금 그대로 동작하지 않는다. Google의 [Gemini API 단종 목록](https://ai.google.dev/gemini-api/docs/deprecations)에 따르면 `text-embedding-004`는 2026년 1월 14일에 종료됐고(권장 대체는 `gemini-embedding-2`), `gemini-2.5-flash`는 2026년 12월 1일부터 다른 모델로 요청이 넘어간다. 책 코드 그대로 키만 넣어도 인덱싱 단계에서 실패한다.

| 역할 | 책 | 이 실습 | 바꾼 위치 |
| --- | --- | --- | --- |
| 임베딩 | `text-embedding-004`, `task_type` 지정 | Ollama `nomic-embed-text`(274MB), `search_document:`, `search_query:` 접두어 | `index.py`의 `OllamaNomicEmbeddings`, `get_embeddings()` |
| 생성 | `gemini-2.5-flash`, `temperature=0` | Ollama `llama3.2`, `temperature=0`, `num_ctx=8192` | `dakka_bot_core.py`의 `get_llm()` |
| 관측 | Langfuse 자체 호스팅 | 같다. 현재 저장소 기준 v4.76.0 | 키를 코드 대신 `.env`에서 |
| 그 밖 | LangChain, FAISS, Chainlit | 같다(저자 `requirements.txt` 버전 고정) | 없음 |

LangChain이 임베딩과 LLM을 같은 인터페이스(`Embeddings`, chat model)로 감싸기 때문에 교체는 이 두 함수 안에서 끝난다. 책이 LangChain의 장점으로 든 "구성 요소 교체"가 실제로 이런 모습이다. Gemini로 되돌리려면 `.env`에서 아래 줄만 바꾸고 인덱스를 새로 만든다. 이 경로는 API 키가 필요하므로 이번 실습에서는 실행하지 않았다.

```text
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=<AI Studio에서 받은 키>
GEMINI_EMBED_MODEL=gemini-embedding-2
GEMINI_MODEL=gemini-2.5-flash
FAISS_INDEX_PATH=./DATA/faiss_index_gemini
```

`GEMINI_EMBED_MODEL`을 생략하면 책과 같은 `text-embedding-004`를 쓰고, 지금은 종료된 모델이라 실패한다. `gemini-embedding-2`가 책의 `task_type` 설정을 그대로 받는지도 키 없이는 확인하지 못했다. `GEMINI_MODEL`은 그 시점의 Gemini 모델 목록에서 고른다. 인덱스 경로를 바꾸는 이유는 [임베딩](#embeddings)에서 설명했듯 다른 모델의 벡터가 섞이지 않게 하기 위해서다.

## UI와 세션 상태 {#ui-session-state}

책은 RAG 로직을 `DakkaBotCore` 클래스로 빼고 UI를 그 위에 얹는다. 같은 클래스를 Chainlit, API 서버, 테스트(`dakka_bot_query` 동기 래퍼)가 함께 쓰게 하려는 것이다. 13장의 promptfoo와 DeepEval도 이 동기 래퍼를 부른다.

Chainlit은 대화형 화면에 필요한 것(스트리밍, 메시지 기록, 첨부 패널)을 Python 몇 줄로 준다. `@cl.on_chat_start`가 새 대화마다 호출되고 `@cl.on_message`가 질문마다 호출된다. `process_query_stream`은 비동기 제너레이터로 `sources`, `token`(여러 번), `done` 순서의 이벤트를 내보내고, 앱은 이것을 받아 "Searching...", "Found 5 relevant documents", 답변 스트리밍으로 화면을 바꾼다. 출처를 먼저 보내는 이유는 사용자가 기다리는 동안 무엇을 근거로 답할지 보여 주기 위해서다.

세션 상태는 코드에서 확인할 것이 많다.

- **봇 인스턴스는 모든 사용자가 공유한다**. 모듈 전역 `dakka_bot = DakkaBotCore()` 하나를 쓰고, 새 대화가 시작될 때마다 `initialize()`가 FAISS 인덱스와 모델 연결을 다시 만든다. 검색기와 모델 연결은 상태가 없어 공유해도 답이 섞이지는 않지만, 여러 사용자가 동시에 대화를 시작하면 같은 객체를 동시에 다시 초기화한다.
- **대화 기억이 없다**. `process_query_stream`은 현재 질문 하나만 받는다. 화면에는 이전 대화가 보여도 모델은 보지 못하므로 "그다음 단계는?" 같은 후속 질문은 문맥을 잃는다. 대화 기록을 넣으려면 `cl.user_session`에 기록을 두고 검색 질의와 프롬프트에 함께 넣어야 하고, 그만큼 토큰 예산이 줄어든다. 이 부분은 코드를 읽고 판단한 것이며 이번 실습에서 후속 질문을 따로 시험하지는 않았다.
- **사용자 식별이 없다**. 저자 코드의 trace metadata는 `"user_session": "demo"`로 고정이다. 비용과 품질을 사용자나 팀별로 보려면 Chainlit 세션 ID나 로그인 사용자를 trace에 넣어야 한다.

## 관측: trace, span, 토큰, 지연, 비용 {#observability}

CPU와 지연 같은 기존 지표는 서비스가 고장 났는지는 알려 주지만 **답이 왜 나쁜지**는 알려 주지 않는다. LLM 앱에서 알고 싶은 것은 "어떤 청크를 찾았고, 모델에 실제로 무엇을 넣었고, 모델이 무엇을 냈고, 각각 얼마나 걸렸고, 토큰을 몇 개 썼는가"다. Langfuse는 이것을 trace 단위로 남긴다.

| 용어 | 뜻 | DakkaBot에서 |
| --- | --- | --- |
| trace | 요청 하나의 전체 기록 | 질문 하나 |
| span | trace 안의 한 단계, 시작과 끝 시간과 입출력 | `dakkabot-query-stream`(전체), `VectorStoreRetriever`(검색) |
| generation | 모델 호출을 기록하는 특별한 span. 모델 이름, 파라미터, 토큰 수, 비용 | `ChatOllama` |
| 첫 토큰 시간 | 요청 시작부터 첫 토큰까지. 스트리밍 UI에서 사용자가 체감하는 대기 | generation의 completion start time |

저자 코드는 LangChain 콜백(`CallbackHandler`)을 **LLM 호출에만** 넘긴다. 그러면 trace에는 generation 하나만 남고 검색 결과는 보이지 않는다. 책은 콜백만 붙이면 검색도 기록된다고 설명하지만, 콜백은 넘겨받은 호출만 기록한다. 실습에서는 질문 하나를 Langfuse span으로 감싸고 retriever 호출에도 같은 콜백을 넘겨, trace 하나가 `dakkabot-query-stream` 아래 `VectorStoreRetriever`와 `ChatOllama`를 갖게 했다([F-1](#ch12-f-1)).

비용은 Langfuse가 모델 이름으로 단가표를 찾아 토큰 수에 곱한 값이다. 책의 화면은 Gemini 호출이라 질문당 비용이 보이지만, `llama3.2`는 단가표에 없어 $0으로 나온다([F-4](#ch12-f-4)). 로컬 모델의 비용은 토큰이 아니라 하드웨어와 시간이다. 이번 PC(노트북 CPU, GPU 없음)에서 1,244토큰 입력, 610토큰 출력 답변 하나에 57초가 걸렸다. 같은 답을 상용 API로 받으면 몇 초와 몇 원 단위다. 운영에서 어느 쪽이 싼지는 요청량과 지연 요구로 정해진다.

trace에는 질문, 검색된 문서, 답변이 모두 들어간다. 사내 문서와 사용자의 질문이 민감하다면 trace 저장소도 같은 등급으로 접근, 보존 기간, 마스킹을 정해야 한다. 책이 자체 호스팅 Langfuse를 쓰는 이유 중 하나다.

## 실패를 나눠 보는 기준 {#failure-taxonomy}

"답이 틀렸다"는 하나의 증상이지만 원인은 단계마다 다르고 고치는 곳도 다르다. trace에서 보는 위치와 함께 정리하면 다음과 같다.

| 실패 | 판별 질문 | trace에서 볼 곳 | 고치는 곳 | 이번 실습에서 본 사례 |
| --- | --- | --- | --- | --- |
| 검색 누락 | 필요한 근거가 상위 k개에 있는가? | `VectorStoreRetriever` 출력 | 분할, 임베딩 모델, k, 질의 재작성 | 직접 만나지 않음. 확인한 질문은 모두 근거가 상위 5개 안에 있었다 |
| 문맥 구성 오류 | 그 근거가 프롬프트에 실제로 들어갔는가, 다른 절차와 섞였는가? | `ChatOllama` 입력 | 청크 형식, 길이 제한, 중복 제거 | 암호화 키 교체 질문에 API 키 교체 절차 청크가 함께 들어감 |
| 생성 오류 | 근거가 있는데 모델이 잘못 읽었는가? | generation 입력과 출력 비교 | 모델, 프롬프트 지시, 출력 형식 | `gemma3:270m`이 무관한 JSON을 복사함 |
| 환각 | 근거에 없는 내용을 지어냈는가? | 출력 문장을 검색 결과와 대조 | 프롬프트, 근거 확인 평가, 더 큰 모델 | `apiVersion: v1`인 Deployment YAML을 만들어 냄(문서에 없음, 잘못된 API 버전) |
| 범위 밖 응답 | 답이 문서에 없을 때 거절하는가? | 검색 거리, 출력 | 거리 임계값, 거절 지시, 가드레일 | 같은 질문에 한 번은 "Canberra"라고 답하고 한 번은 거절함 |

"How do I rotate encryption keys?"의 답이 좋은 예다. 1단계(키 교체 API 호출)는 문서의 `key-management-service` API를 정확히 인용했다. 그런데 3단계는 같은 검색 결과에 섞여 들어온 **API 키** 교체 절차의 "Update applications with new key"를 암호화 키 교체 절차로 가져왔고, 그 과정에서 문서에 없는 Deployment YAML을 지어냈다. 출처 5개는 모두 그럴듯했고 화면만 보면 근거 있는 답처럼 보인다. trace에서 검색 출력과 생성 입력을 나란히 보면 어디서 섞였는지 보인다. 이런 사례를 정답 근거와 함께 질문 집합으로 모아 두는 것이 13장 평가의 재료다.

검색 품질과 답변 품질은 따로 잰다. 검색은 질문마다 정답 근거 청크를 정해 두고 상위 k개에 포함되는지(Recall@k)를 보고, 답변은 정답성, 근거 충실성, 관련성, 거절 여부를 본다. 전체 점수 하나로는 검색과 모델과 프롬프트 중 무엇을 바꿨을 때 좋아졌는지 구분할 수 없다.

## 책 코드와 실제 저장소의 차이 {#book-code-gaps}

12장 코드는 저자 저장소 [practical-mlops/dakkabot](https://github.com/practical-mlops/dakkabot)에 있다. 이 글은 `main`의 최신 커밋 `8d16c23`(2025-07-17)을 기준으로 했다. 12장 내용은 그 앞의 `5467828`(최소 RAG)부터 `77fb0b0`(스트리밍)까지이고, 마지막 두 커밋은 13장의 promptfoo와 DeepEval을 더한다. 실행하면서 확인한 차이는 다음과 같다.

| 위치 | 책 | 저장소와 실제 동작 | 이 실습의 처리 |
| --- | --- | --- | --- |
| 리스팅 12.2 | `from langchain.callbacks import LangfuseCallbackHandler` | 그런 경로는 없다. 저장소는 `from langfuse.langchain import CallbackHandler`(Langfuse SDK v3) | 저장소 방식 |
| 리스팅 12.19 | Langfuse 키를 환경 변수에서 읽음 | `dakka_bot_core.py`와 `minimal_rag_with_tracing.py`에 키가 문자열로 박혀 있음 | 환경 변수(`.env`)로 |
| 12.4.2 | 콜백만 붙이면 검색도 기록 | 콜백을 LLM 호출에만 넘겨 trace에 생성 단계만 남음 | span으로 감싸고 retriever에도 콜백 |
| 12.3 | UI가 출처를 표시 | `sources`를 받아 두고 표시하지 않음 | "Sources" 줄과 출처 패널 추가 |
| 리스팅 12.13 | "기본 3개 대신 5개" | LangChain retriever 기본값은 4개 | 설명만 |
| 12.2.4 | "200토큰 겹침" | `RecursiveCharacterTextSplitter`는 문자 수 기준 | 설명만 |
| `requirements.txt` | 해당 없음 | `index.py`가 쓰는 `tqdm`이 목록에 없음. 13장 패키지 없이 설치하면 `ModuleNotFoundError` | `tqdm` 추가 설치 |
| `guardrail_helpers.py` | 리스팅 12.17이 import | Guardrails Hub 검증기(계정 토큰 필요)가 있어야 import되고, import할 때 `OTEL_SDK_DISABLED=true`를 설정해 **같은 프로세스의 Langfuse 기록을 조용히 끈다** | 13장 전까지 import하지 않음 |
| `process_query_stream` | 해당 없음 | UI가 `done`을 받고 반복을 멈추므로, span을 제너레이터 끝까지 열어 두면 OpenTelemetry 문맥 해제 오류가 난다 | `done` 전에 span을 닫음 |
| 12.2.3 | `text-embedding-004`, `gemini-2.5-flash` | 각각 종료, 단종 예정 | 로컬 모델로 교체, 모델 이름을 환경 변수로 |
| 12.4.1 | `git clone` 뒤 `docker compose up` | 지금 저장소는 Langfuse v4이고 AI gateway 서비스가 추가됐다. 이 PC에서는 9000, 6379 포트가 이미 쓰여 그대로는 뜨지 않음 | 포트를 덮어쓰는 override 파일 |

`OTEL_SDK_DISABLED` 문제는 가장 찾기 어려웠다. 오류 메시지가 전혀 없고, 같은 코드를 별도 스크립트로 돌리면 trace가 남는데 Chainlit 앱에서만 남지 않는다. Langfuse SDK v3가 OpenTelemetry 위에서 동작하게 바뀌면서, 다른 라이브러리의 OpenTelemetry 끄기 설정이 Langfuse까지 끄게 된 것이다. 13장에서 가드레일을 켤 때도 이 설정을 import 뒤에 되돌려야 한다.

## 이 장이 남기는 한계 {#remaining-limits}

DakkaBot은 검색, 문맥 구성, 생성을 나누고 그 과정을 trace로 남기는 데까지 왔다. 실행해 보면 남는 일도 분명하다.

- **평가가 없다**. 이번 실습의 판단은 사람이 화면과 trace를 읽고 한 것이다. 정답 근거가 달린 질문 집합과 자동 채점이 없으면 프롬프트나 k를 바꿨을 때 좋아졌는지 알 수 없다.
- **범위 밖 질문을 막지 못한다**. 임계값이 없어 무관한 질문에도 출처 5개가 붙고, 거절 여부는 실행마다 달랐다.
- **프롬프트가 코드 안의 문자열이다**. 프롬프트를 바꾸면 코드를 배포해야 하고, 어떤 버전의 프롬프트가 어떤 trace를 만들었는지 연결되지 않는다.
- **권한과 갱신이 없다**. 모든 사용자가 모든 문서를 검색하고, 문서가 바뀌면 인덱스 전체를 다시 만든다. 대화 기억과 사용자 식별도 없다.
- **비용이 보이지 않는다**. 로컬 모델은 단가표가 없어 $0이고, 상용 모델로 바꾸면 질문 유형별 토큰 비용을 따로 봐야 한다.

13장은 이 중 프롬프트 관리와 테스트, 가드레일, 비용과 거버넌스를 다룬다. 그림의 ⑩이 그 연결이다.

## 실습 순서 {#book-ch12-sop}

로컬 모델을 준비하고, 저자 코드를 로컬 제공자로 고친 뒤, 인덱스를 만들고 Langfuse를 띄워 Chainlit 화면에서 질문한다. 마지막으로 trace에서 검색과 생성을 나눠 본다. 아래 출력과 화면은 2026년 11월 8일 이 순서대로 실행해 얻은 것이다. 실행 환경은 Windows 11 노트북(13세대 Core i7, RAM 64GB, GPU 없음), Docker Desktop, Ollama 0.40.12다. 쿠버네티스 클러스터는 쓰지 않는다.

```mermaid
flowchart LR
    accTitle: 12장 실습 순서
    accDescr: Ollama와 모델, 저자 코드와 가상환경을 준비하고, 저자 코드를 로컬 제공자로 고친다. 인덱스를 만들어 검색을 확인하고, Langfuse를 띄운 뒤 Chainlit 화면에서 질문한다. 이어 Langfuse trace로 검색과 생성을 나눠 보고 정리한다.
    A["A. 준비"] --> B["B. 로컬 제공자로 코드 고치기"]
    B --> C["C. 인덱스와 검색 확인"]
    A --> D["D. Langfuse 띄우기"]
    C --> E["E. DakkaBot 화면에서 질문"]
    D --> E
    E --> F["F. trace로 실패 나눠 보기"]
    F --> G["G. 문제 해결과 정리"]
```

| 구간 | 끝났을 때 남는 것 |
| --- | --- |
| A. 준비 | Ollama의 `llama3.2`, `nomic-embed-text`, 저자 코드 `ch12\dakkabot`, 가상환경 `ch12\venv` |
| B. 로컬 제공자로 코드 고치기 | 제공자를 고르는 `get_embeddings()`, `get_llm()`, trace span, 출처 표시, `.env` |
| C. 인덱스와 검색 확인 | `DATA\faiss_index`(청크 345개), 질문별 검색 거리 |
| D. Langfuse 띄우기 | `ch12-langfuse` 컨테이너 6개, 프로젝트 `dakkabot`과 API 키 |
| E. DakkaBot 화면에서 질문 | 근거 있는 답과 범위 밖 질문의 화면, 출처 패널 |
| F. trace로 실패 나눠 보기 | 검색 span, generation, 토큰과 비용 화면, 모델 크기 비교 |
| G. 문제 해결과 정리 | 멈춘 서버, 13장에서 다시 켜는 방법 |

명령은 PowerShell에서 실행하고, 작업 폴더 아래 `ch12\`를 만들어 그 안에 저자 코드(`ch12\dakkabot`), 가상환경(`ch12\venv`), Langfuse 설정(`ch12\langfuse`)을 둔다. 프롬프트 앞의 폴더 표시가 없으면 작업 폴더에서 실행한다.

## A. 준비 {#ch12-a}

지금 위치: 전체 그림의 ②, ⑤, ⑥이 쓸 모델과 코드를 준비한다.

### A-1. 디스크와 도구 확인 {#ch12-a-1}

1. 남은 디스크를 확인한다. 이번 실습이 새로 쓰는 공간은 `llama3.2` 2.0GB, `nomic-embed-text` 274MB, Langfuse 이미지 약 3.4GB(langfuse 1.03GB, worker 803MB, ClickHouse 1.19GB, MinIO 236MB, Redis 170MB, Postgres 17-alpine은 이미 있던 것을 썼다), 가상환경 약 250MB다. Docker 이미지는 Docker Desktop의 가상 디스크 파일 안에 쌓이고, 이미지를 지워도 그 파일은 자동으로 줄지 않는다.
   ```powershell
   "{0:N1} GB" -f ((Get-PSDrive C).Free/1GB)
   ```
2. Ollama를 설치하고 버전을 확인한다. 설치하면 백그라운드 서비스가 `http://127.0.0.1:11434`에서 기다린다.
   ```powershell
   winget install Ollama.Ollama
   ollama --version
   ```
   ```text
   ollama version is 0.40.12
   ```
3. Docker Desktop이 켜져 있는지, 그리고 Langfuse가 쓸 포트 3000, 9090과 Chainlit의 8000이 비어 있는지 본다. 아무것도 나오지 않으면 비어 있는 것이다.
   ```powershell
   docker version --format '{{.Server.Version}}'
   Get-NetTCPConnection -State Listen -LocalPort 3000,8000,9090 -ErrorAction SilentlyContinue
   ```

### A-2. 모델 내려받기 {#ch12-a-2}

1. 생성 모델과 임베딩 모델을 받는다. 이번 PC에는 `llama3.2`가 이미 있어서 `nomic-embed-text`만 새로 받았다. 디스크가 부족하면 `llama3.2:1b`(1.3GB)를 받고 B-4의 `OLLAMA_MODEL`을 바꾼다. 1B 모델은 이 글에서 실행하지 않았다.
   ```powershell
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ollama list
   ```
   ```text
   NAME                       ID              SIZE      MODIFIED
   nomic-embed-text:latest    0a109f422b47    274 MB    14 seconds ago
   llama3.2:latest            a80c4f17acd5    2.0 GB    9 months ago
   gemma3:270m                e7d36fb2c3b3    291 MB    10 months ago
   ```
   출력은 이 실습과 관련된 줄만 남겼다. `gemma3:270m`은 원래 있던 모델로 [F-5](#ch12-f-5)의 비교에만 쓰며, 따라 할 때는 `ollama pull gemma3:270m`(291MB)으로 받는다.

### A-3. 저자 코드와 가상환경 {#ch12-a-3}

1. 저자 저장소를 받고 이 글에서 확인한 커밋으로 고정한다.
   ```powershell
   git clone https://github.com/practical-mlops/dakkabot.git ch12\dakkabot
   git -C ch12\dakkabot checkout 8d16c23
   ```
   `DATA\docs_1.md`~`docs_5.md`가 DataKrypt의 가상 사내 문서다. API 문서, 운영 절차, 보안 규정이 섞여 있다.
2. 가상환경을 만들고 패키지를 설치한다. 버전은 저자 `requirements.txt`와 같고, `langchain-ollama`와 `tqdm`을 더했다. `guardrails-ai`, `deepeval`, `flashrank`는 13장에서 쓰므로 여기서는 설치하지 않는다. Gemini 패키지는 되돌릴 때를 위해 그대로 둔다.
   ```powershell
   uv venv ch12\venv --python 3.12
   uv pip install --python ch12\venv langchain==0.3.26 langchain-community==0.3.27 langchain-google-genai==2.1.7 google-genai==1.25.0 faiss-cpu==1.11.0 dotenv==0.9.9 langfuse==3.1.3 chainlit==2.6.2 langchain-ollama==0.3.6 tqdm
   ```

완료 기준: `ollama list`에 두 모델이 보이고, `ch12\venv\Scripts\python.exe -c "import langchain_ollama, faiss, chainlit, langfuse; print('ok')"`가 `ok`를 출력한다.

## B. 로컬 제공자로 코드 고치기 {#ch12-b}

지금 위치: 전체 그림의 ②, ⑤, ⑥, ⑧. 임베딩과 생성 제공자를 바꾸고, 관측과 출처 표시의 빈틈을 메운다. 고친 파일은 세 개이고 모두 `ch12\dakkabot` 안에 있다.

### B-1. 임베딩: index.py {#ch12-b-1}

1. 파일 위쪽의 `from google import genai`, `from google.genai import types`를 지우고 `import os`를 더한다. Google 패키지는 Gemini를 쓸 때만 불러오도록 `GeminiEmbeddings.__init__` 안으로 옮기고, 모델 이름을 환경 변수로 받는다.
   ```python
   class GeminiEmbeddings(Embeddings):
       def __init__(self):
           from google import genai
           from google.genai import types
           self.types = types
           # text-embedding-004 was shut down on 2026-01-14; set GEMINI_EMBED_MODEL=gemini-embedding-2
           self.model = os.getenv("GEMINI_EMBED_MODEL", "text-embedding-004")
           self.client = genai.Client()
       # embed_documents, embed_query: model=self.model, config=self.types.EmbedContentConfig(...)
   ```
2. 같은 자리에 로컬 임베딩 클래스와 선택 함수를 더한다. 책의 `task_type` 구분을 `nomic-embed-text`의 접두어로 옮긴 것이다.
   ```python
   class OllamaNomicEmbeddings(Embeddings):
       def __init__(self):
           from langchain_ollama import OllamaEmbeddings
           self.model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
           self.client = OllamaEmbeddings(model=self.model)

       def embed_documents(self, texts: List[str]) -> List[List[float]]:
           embeddings = []
           for text in tqdm(texts, desc="Embedding documents"):
               embeddings.append(self.client.embed_query(f"search_document: {text}"))
           return embeddings

       def embed_query(self, text: str) -> List[float]:
           return self.client.embed_query(f"search_query: {text}")


   def get_embeddings() -> Embeddings:
       if os.getenv("EMBEDDING_PROVIDER", "ollama").lower() == "gemini":
           return GeminiEmbeddings()
       return OllamaNomicEmbeddings()


   INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./DATA/faiss_index")
   ```
3. `create_faiss_index`와 `load_index`의 `GeminiEmbeddings()`를 `get_embeddings()`로, `save_index`와 `load_index`의 기본 경로 `"./DATA/faiss_index"`를 `INDEX_PATH`로 바꾼다.

### B-2. 생성과 trace: dakka_bot_core.py {#ch12-b-2}

1. `ChatGoogleGenerativeAI` import와 `from index import GeminiEmbeddings`를 지우고, 제공자를 고르는 함수를 둔다.
   ```python
   from index import get_embeddings, INDEX_PATH


   def get_llm():
       if os.getenv("LLM_PROVIDER", "ollama").lower() == "gemini":
           from langchain_google_genai import ChatGoogleGenerativeAI
           return ChatGoogleGenerativeAI(
               model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
               temperature=0.0,
               google_api_key=os.environ["GEMINI_API_KEY"],
               convert_system_message_to_human=True
           )
       from langchain_ollama import ChatOllama
       return ChatOllama(
           model=os.getenv("OLLAMA_MODEL", "llama3.2"),
           temperature=0.0,
           # Ollama silently truncates prompts longer than num_ctx
           num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
       )
   ```
2. `initialize()`에서 임베딩, 인덱스 경로, 모델, Langfuse 키를 바꾼다. 키는 리스팅 12.19처럼 환경 변수에서 읽는다.
   ```python
   embeddings = get_embeddings()
   self.vector_store = FAISS.load_local(INDEX_PATH, embeddings=embeddings,
                                        allow_dangerous_deserialization=True)
   ...
   self.llm = get_llm()
   self.langfuse = Langfuse(
       public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
       secret_key=os.environ["LANGFUSE_SECRET_KEY"],
       host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
   )
   self.langfuse_handler = CallbackHandler()
   ```
3. `process_query_stream`의 본문을 span 하나로 감싸고, retriever에도 콜백을 넘긴다. 그리고 `done`은 span을 닫은 **뒤에** 보낸다. Chainlit이 `done`을 받으면 반복을 멈추기 때문에, span이 그 뒤까지 열려 있으면 닫히지 못하고 OpenTelemetry가 `Failed to detach context` 오류를 낸다. 실제로 처음에는 이 오류가 났다. `process_query`도 같은 방식으로 span(`dakkabot-query`)을 둔다.
   ```python
   try:
     with self.langfuse.start_as_current_span(name="dakkabot-query-stream", input={"query": query}) as span:
       docs = self.retriever.invoke(query, config={"callbacks": [self.langfuse_handler]})
       ...                                   # sources를 yield, context와 prompt 구성(저자 코드 그대로)
       answer = []
       async for chunk in self.llm.astream(prompt, config={"callbacks": [self.langfuse_handler]}):
           if chunk.content:
               answer.append(chunk.content)
               yield {"type": "token", ...}
       span.update(output="".join(answer))
       span.update_trace(input={"query": query}, output="".join(answer),
                         metadata={"doc_count": len(docs), "context_length": len(context)})
     self.langfuse.flush()
     yield {"type": "done", "content": None, "sources": sources, "doc_count": len(docs)}
   except Exception as e:
       ...
   ```
   들여쓰기 두 칸은 저자 코드의 나머지 줄을 건드리지 않으려고 `with`만 끼워 넣은 흔적이다. 새로 쓴다면 본문 전체를 한 단계 들여쓴다.

### B-3. 화면: chainlit_app_streaming.py {#ch12-b-3}

1. `from guardrail_helpers import validate_user_inputs`를 아래로 바꾼다. 13장 전까지는 입력을 그대로 통과시킨다. 이 import가 `OTEL_SDK_DISABLED=true`를 설정해 Langfuse 기록을 끄기 때문이다.
   ```python
   import os

   if os.getenv("ENABLE_GUARDRAILS", "false").lower() == "true":
       from guardrail_helpers import validate_user_inputs
   else:
       def validate_user_inputs(text: str):
           return text, True
   ```
2. `chunk["type"] == "done"` 분기에서 `response_msg.send()` 앞에 출처를 붙인다. `cl.Text`의 `name`이 답변 본문에 나오면 Chainlit이 그 이름을 눌러 원문을 여는 링크로 바꾼다.
   ```python
   if sources_info:
       names = []
       for src in sources_info["sources"]:
           name = f"[{src['index']}] {src['source']}"
           names.append(name)
           response_msg.elements.append(
               cl.Text(name=name, content=src["full_content"], display="side"))
       await response_msg.stream_token("\n\n**Sources:** " + ", ".join(names))
   ```

### B-4. 설정 파일 .env {#ch12-b-4}

1. `ch12\dakkabot\.env`를 만든다. 저자 저장소의 `.gitignore`가 이 파일을 제외한다. Langfuse 키는 D-1에서 Langfuse가 처음 뜰 때 만들게 할 로컬 전용 값이다.
   ```text
   LLM_PROVIDER=ollama
   OLLAMA_MODEL=llama3.2
   OLLAMA_NUM_CTX=8192
   EMBEDDING_PROVIDER=ollama
   OLLAMA_EMBED_MODEL=nomic-embed-text
   FAISS_INDEX_PATH=./DATA/faiss_index
   LANGFUSE_PUBLIC_KEY=pk-lf-ch12-local
   LANGFUSE_SECRET_KEY=sk-lf-ch12-local
   LANGFUSE_HOST=http://localhost:3000
   ```

완료 기준: `ch12\dakkabot`에서 `..\venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); import index, dakka_bot_core; print('import ok')"`가 `import ok`를 출력한다.

## C. 인덱스와 검색 확인 {#ch12-c}

지금 위치: 전체 그림의 ①~③과 ⑤. 생성 모델 없이 검색만 먼저 확인한다. 검색이 맞아야 뒤 단계의 결과를 해석할 수 있다.

### C-1. 인덱스 만들기 {#ch12-c-1}

1. 저자 코드 폴더에서 `index.py`를 실행한다. 문서를 읽고, 자르고, 청크마다 임베딩을 받아 FAISS 인덱스로 저장한 뒤 시험 질문 하나로 검색한다.
   ```powershell
   cd ch12\dakkabot
   ..\venv\Scripts\python.exe index.py
   ```
   ```text
   INFO:__main__:Loaded 5 documents
   INFO:__main__:Created 345 chunks
   INFO:__main__:Creating FAISS index with OllamaNomicEmbeddings...
   Embedding documents: 100%|##########| 345/345 [01:31<00:00,  3.76it/s]
   INFO:__main__:Created index with 345 chunks
   INFO:__main__:Saved index to ./DATA/faiss_index
   INFO:__main__:Found 3 results:
   INFO:__main__:1. encryption_result, test_data
   INFO:__main__:2. **Diagnosis:**
   INFO:__main__:3. # Key Management
   ```
   httpx 요청 로그는 뺐다. 345개 청크를 하나씩 임베딩하는 데 CPU에서 1분 31초가 걸렸다. 책이 "인덱스를 매번 다시 만들 수 없다"며 저장을 강조하는 이유가 여기서 보인다. 상용 API라면 시간과 함께 요청 수만큼 비용이 든다.
2. 저장된 파일을 확인한다.
   ```powershell
   Get-ChildItem DATA\faiss_index | Select-Object Name, Length
   ```
   ```text
   Name         Length
   ----         ------
   index.faiss 1059885
   index.pkl    294104
   ```
   `index.faiss`는 345개 × 768차원 × 4바이트(float32)에 머리글을 더한 크기다. `index.pkl`이 청크 원문과 `source` 메타데이터다.

### C-2. 검색 거리 보기 {#ch12-c-2}

1. 질문마다 상위 5개 청크와 거리를 찍는 `retrieval_probe.py`를 `ch12\dakkabot`에 만든다.
   ```python
   import sys
   sys.stdout.reconfigure(encoding="utf-8")
   from dotenv import load_dotenv; load_dotenv()
   from langchain_community.vectorstores import FAISS
   from index import get_embeddings, INDEX_PATH

   store = FAISS.load_local(INDEX_PATH, get_embeddings(), allow_dangerous_deserialization=True)
   questions = sys.argv[1:] or [
       "How do I rotate encryption keys?",
       "How often should production API keys be rotated?",
       "What is the capital of Australia?",
   ]
   for q in questions:
       print(f"\n## {q}")
       for doc, dist in store.similarity_search_with_score(q, k=5):
           first = doc.page_content.strip().splitlines()[0][:60]
           print(f"  L2={dist:.3f}  {doc.metadata['source']}  | {first}")
   ```
2. 실행한다.
   ```powershell
   ..\venv\Scripts\python.exe retrieval_probe.py
   ```
   ```text
   ## How do I rotate encryption keys?
     L2=0.558  DATA\docs_4.md  | encryption_result, test_data
     L2=0.570  DATA\docs_1.md  | **Diagnosis:**
     L2=0.611  DATA\docs_1.md  | # Key Management
     L2=0.641  DATA\docs_1.md  | #### key-management-service API Reference
     L2=0.648  DATA\docs_1.md  | 5. **Post-Incident (24-72 hours)**

   ## How often should production API keys be rotated?
     L2=0.389  DATA\docs_1.md  | 5. **Post-Incident (24-72 hours)**
     L2=0.629  DATA\docs_1.md  | #### key-management-service API Reference
     L2=0.631  DATA\docs_1.md  | # Key Management
     L2=0.667  DATA\docs_1.md  | **Diagnosis:**
     L2=0.732  DATA\docs_2.md  | **Query Parameters:**

   ## What is the capital of Australia?
     L2=0.936  DATA\docs_5.md  | 'geographic_location': 'US_CA'
     L2=0.951  DATA\docs_1.md  | cpu: "250m"
     L2=0.988  DATA\docs_2.md  | **Query Parameters:**
     L2=0.994  DATA\docs_3.md  | 'estimated_value': current_usage['monthly_spend'] * 0.8,
     L2=0.998  DATA\docs_4.md  | ### ai-service API Reference
   ```
   첫 질문의 4번째 청크에 키 교체 API(`POST /rotate/{key_id}`)가, 5번째 청크에 **API 키** 교체 주기와 절차가 들어 있다. 암호화 키를 물었는데 API 키 절차도 함께 들어간다는 뜻이고, E-2의 답에서 그 결과를 본다. 세 번째 질문은 거리가 모두 0.93 이상이지만 그래도 5개가 돌아온다.

완료 기준: `DATA\faiss_index`에 두 파일이 있고, 문서 안 질문과 범위 밖 질문의 거리 차이를 설명할 수 있다.

## D. Langfuse 띄우기 {#ch12-d}

지금 위치: 전체 그림의 ⑧, ⑨를 받을 곳을 만든다. 책처럼 Langfuse 저장소의 `docker-compose.yml`을 쓰되, 이 PC에 맞게 덮어쓰는 파일을 하나 더 둔다.

### D-1. compose 파일과 덮어쓰기 {#ch12-d-1}

1. 책은 저장소 전체를 `git clone`하지만 필요한 것은 compose 파일 하나다. 이 글에서 확인한 커밋의 파일만 받는다.
   ```powershell
   mkdir ch12\langfuse
   Invoke-WebRequest https://raw.githubusercontent.com/langfuse/langfuse/b9529a9336d5854d5970b7b1c91b8d92a41db5dd/docker-compose.yml -OutFile ch12\langfuse\docker-compose.yml
   ```
   이 파일은 Langfuse v4 기준이다. web, worker 외에 ClickHouse(trace 저장), Postgres(사용자, 프로젝트, 키), Redis(작업 큐), MinIO(원본 이벤트와 미디어)를 함께 띄우고, 책 이후에 생긴 AI gateway 서비스도 들어 있다.
2. 버전을 고정하는 `ch12\langfuse\.env`를 만든다. Postgres는 이 PC에 이미 있던 `17-alpine` 이미지를 쓰게 했다.
   ```text
   POSTGRES_VERSION=17-alpine
   LANGFUSE_IMAGE_TAG=4.76.0
   ```
3. `ch12\langfuse\docker-compose.override.yml`을 만든다. 원본은 ClickHouse를 호스트 9000, Redis를 6379, Postgres를 5432에 연다. 이 PC는 앞 장의 클러스터 포트포워딩이 9000과 6379를 쓰고 있어 그대로는 뜨지 않는다. 컨테이너끼리만 쓰는 포트는 호스트에 열 필요가 없으므로 지운다(`!reset`, `!override`는 Compose 2.24 이상). 처음 뜰 때 조직, 프로젝트, 관리자, API 키를 만들게 하는 `LANGFUSE_INIT_*` 값도 넣는다. 책처럼 화면에서 가입하고 키를 만들어도 결과는 같다.
   ```yaml
   services:
     langfuse-worker:
       ports: !reset []
       environment:
         TELEMETRY_ENABLED: "false"
     langfuse-web:
       environment:
         TELEMETRY_ENABLED: "false"
         LANGFUSE_INIT_ORG_ID: ch12-org
         LANGFUSE_INIT_ORG_NAME: DataKrypt
         LANGFUSE_INIT_PROJECT_ID: ch12-dakkabot
         LANGFUSE_INIT_PROJECT_NAME: dakkabot
         LANGFUSE_INIT_PROJECT_PUBLIC_KEY: pk-lf-ch12-local
         LANGFUSE_INIT_PROJECT_SECRET_KEY: sk-lf-ch12-local
         LANGFUSE_INIT_USER_EMAIL: admin@datakrypt.local
         LANGFUSE_INIT_USER_NAME: admin
         LANGFUSE_INIT_USER_PASSWORD: ch12-local-password
     clickhouse:
       ports: !reset []
     redis:
       ports: !reset []
     postgres:
       ports: !reset []
     minio:
       ports: !override
         - 127.0.0.1:9090:9000
   ```
   원본 파일의 `# CHANGEME` 비밀번호(Postgres, ClickHouse, Redis, MinIO, `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`)는 로컬 실습이라 그대로 뒀다. 다른 사람이 접근할 수 있는 곳에 띄운다면 모두 바꿔야 한다.

### D-2. 실행과 로그인 {#ch12-d-2}

1. web과 worker만 지정해 띄운다. 의존하는 저장소 서비스는 함께 뜨고, AI gateway는 받지도 띄우지도 않는다. 프로젝트 이름 `ch12-langfuse`가 컨테이너와 볼륨 이름의 앞에 붙는다.
   ```powershell
   cd ch12\langfuse
   docker compose -p ch12-langfuse up -d langfuse-web langfuse-worker
   ```
   ```text
    Container ch12-langfuse-redis-1 Healthy
    Container ch12-langfuse-minio-1 Healthy
    Container ch12-langfuse-clickhouse-1 Healthy
    Container ch12-langfuse-langfuse-worker-1 Started
    Container ch12-langfuse-langfuse-web-1 Started
   ```
   처음에는 이미지 내려받기에 몇 분이 걸린다.
2. 상태를 확인한다.
   ```powershell
   (Invoke-WebRequest http://localhost:3000/api/public/health -UseBasicParsing).Content
   ```
   ```text
   {"status":"OK","version":"4.76.0"}
   ```
3. http://localhost:3000 에서 `admin@datakrypt.local`, `ch12-local-password`로 로그인하면 조직 DataKrypt 아래 프로젝트 `dakkabot`이 있다. 아직 trace는 없다.

완료 기준: health가 `OK`이고 로그인할 수 있다.

## E. DakkaBot 화면에서 질문 {#ch12-e}

지금 위치: 전체 그림의 ④~⑧. 질문 하나가 검색, 생성, 스트리밍, 기록을 모두 지나간다.

### E-1. Chainlit 실행 {#ch12-e-1}

1. 새 터미널에서 저자 코드 폴더로 가서 Chainlit을 띄운다. 책의 `chainlit run`과 같고, `--headless`는 브라우저를 자동으로 열지 않는 옵션이다. 이 터미널은 E와 F가 끝날 때까지 열어 둔다.
   ```powershell
   cd ch12\dakkabot
   ..\venv\Scripts\chainlit.exe run chainlit_app_streaming.py --headless --port 8000
   ```
   ```text
   2026-11-08 10:00:37 - Loaded .env file
   2026-11-08 10:00:39 - Your app is available at http://localhost:8000
   ```
2. http://localhost:8000 을 연다. 저자 코드의 시작 메시지("DakkaBot is starting up...", "DakkaBot Ready!")가 차례로 나온다. 이때 `initialize()`가 FAISS 인덱스를 읽고 Langfuse 클라이언트를 만든다.

### E-2. 문서에 답이 있는 질문 {#ch12-e-2}

1. `How do I rotate encryption keys?`를 보낸다. "Searching DataKrypt documentation..."이 "Found 5 relevant documents. Generating response..."로 바뀌고, 첫 토큰이 오면 사라지며 답이 흘러나온다. 이번 실행에서 답이 끝나기까지 57초가 걸렸다.

   ![DakkaBot 답변 앞부분. 질문 How do I rotate encryption keys? 아래 1단계로 key-management-service의 POST https://api.datakrypt.com/keys/v1/rotate/{key_id} 호출과 rotation_strategy, notification_webhook JSON 예시를 제시한다.](/images/ml-platform-engineering/sop/ch12-chat-grounded-top.png)

   1단계의 엔드포인트와 요청 본문은 C-2의 4번째 청크(`key-management-service API Reference`)에 그대로 있다. 근거 있는 부분이다.
2. 답 끝까지 내려 출처를 본다.

   ![DakkaBot 답변 끝부분. 새 키 확인 curl 예시와 Additional Tips 아래에 Sources 줄로 [1] DATA\docs_4.md, [2]~[5] DATA\docs_1.md가 붙어 있다.](/images/ml-platform-engineering/sop/ch12-chat-grounded-sources.png)

   "Sources" 줄은 B-3에서 더한 부분이다. 저자 코드 그대로면 이 줄이 없다.
3. 출처 이름을 누르면 오른쪽 패널에 그 청크 원문이 열린다.

   ![[1] DATA\docs_4.md 출처 패널. 청크 원문은 key-management-service의 rotate_key를 호출하는 통합 테스트 코드다.](/images/ml-platform-engineering/sop/ch12-chat-source-panel.png)

   가장 가까운 청크가 절차 문서가 아니라 **테스트 코드**였다. 사람에게 "어떻게 하나"를 알려 주는 문서보다 같은 단어가 많이 나오는 코드가 더 가까웠던 것이다. 3단계 "새 키로 애플리케이션 갱신"과 4단계 "새 키 확인"은 5번째 청크의 **API 키** 교체 절차에서 왔고, 3단계에 붙은 Deployment YAML(`apiVersion: v1`)은 어느 청크에도 없다. 화면만 보면 출처 5개가 붙은 근거 있는 답이지만, 실제로는 근거 있는 부분, 다른 절차가 섞인 부분, 지어낸 부분이 함께 있다. [실패를 나눠 보는 기준](#failure-taxonomy)의 문맥 구성 오류와 환각이다.

### E-3. 문서에 답이 없는 질문 {#ch12-e-3}

1. `What is the capital of Australia?`를 보낸다.

   ![범위 밖 질문에 대한 DakkaBot 답변. 질문이 제공된 문서와 관련 없다고 말하고 DataKrypt API에 대해 다시 물어 달라고 한다. 그래도 Sources로 docs_5, docs_1, docs_2, docs_3, docs_4 다섯 개가 붙어 있다.](/images/ml-platform-engineering/sop/ch12-chat-out-of-scope.png)

   이번에는 답하지 않았다. 하지만 C-2에서 본 것처럼 거리가 0.93 이상인 무관한 청크 5개가 그대로 "출처"로 붙었다. 사용자가 출처를 근거로 믿으면 오해가 생긴다.
2. 같은 질문을 UI 없이 동기 래퍼로 다시 보낸다. 13장의 테스트 도구가 쓰는 함수다.
   ```powershell
   ..\venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); from dakka_bot_core import dakka_bot_query; print(dakka_bot_query('What is the capital of Australia?'))"
   ```
   이 질문은 UI로 두 번, 동기 래퍼로 두 번, 모두 같은 프롬프트(입력 665토큰)와 temperature 0으로 실행했다. 세 번은 위 화면처럼 거절했고, 동기 래퍼의 한 번은 마지막 문단에 이렇게 답했다.
   ```text
   If you're looking for general information on Australia's capital, I can try to provide that as well.
   According to my knowledge, the capital of Australia is Canberra.
   ```
   "DataKrypt 정보에 집중하라"는 지시가 있어도 모델의 일반 지식이 새어 나온다. 그리고 그 여부가 실행마다 다르다. 거절을 보장하려면 거리 임계값으로 생성 전에 막거나, 13장의 가드레일과 평가로 확인해야 한다.

완료 기준: 두 질문의 답과 출처를 화면에서 확인했고, 첫 답에서 근거 있는 부분과 섞인 부분을 구분할 수 있다.

## F. trace로 실패 나눠 보기 {#ch12-f}

지금 위치: 전체 그림의 ⑧, ⑨. E에서 본 답이 어느 단계에서 어떻게 만들어졌는지 Langfuse에서 확인한다.

### F-1. trace 목록과 트리 {#ch12-f-1}

1. Langfuse의 Tracing 화면에서 Name 필터를 `dakkabot-query-stream`으로 고른다. UI에서 보낸 질문은 이 이름, 동기 래퍼로 보낸 질문은 `dakkabot-query`로 남는다.

   ![Langfuse Tracing 목록. 이름 dakkabot-query-stream인 trace 4개가 시간순으로 있고 Input 열에 질문, Output 열에 답변 앞부분이 보인다.](/images/ml-platform-engineering/sop/ch12-langfuse-traces.png)

2. 암호화 키 질문의 행을 누른다.

   ![trace 상세. dakkabot-query-stream 57.27초 아래 VectorStoreRetriever 0.06초와 ChatOllama 57.21초, 1,854 tokens가 트리로 보이고 오른쪽에 질문과 최종 답이 있다.](/images/ml-platform-engineering/sop/ch12-langfuse-trace-tree.png)

   57초 중 검색은 0.06초이고 나머지가 생성이다. 지연을 줄이려면 검색이 아니라 모델과 프롬프트 길이를 봐야 한다는 뜻이다. 저자 코드 그대로라면 이 트리에 `ChatOllama` 하나만 있고, 검색이 무엇을 돌려줬는지는 남지 않는다.

### F-2. 검색 span {#ch12-f-2}

1. 트리에서 `VectorStoreRetriever`를 누른다.

   ![VectorStoreRetriever span. Input은 질문이고 Output에는 Document 목록이 있으며 펼친 문서의 page_content에 Key Management 설정 DEFAULT_ALGORITHM=AES-256-GCM, KEY_ROTATION_SCHEDULE=90d가 보인다.](/images/ml-platform-engineering/sop/ch12-langfuse-retriever.png)

   출력 문서 5개를 차례로 펼쳐 보면 C-2와 같은 청크들이다. 답에 섞인 API 키 절차가 다섯 번째 문서에 있는 것도 여기서 확인된다. "필요한 근거를 찾았는가"(검색 누락인가)는 이 span에서 판단한다.

### F-3. generation {#ch12-f-3}

1. 트리에서 `ChatOllama`를 누른다.

   ![ChatOllama generation. User 메시지에 You are DakkaBot으로 시작하는 지시가 있고 Documentation Context와 Document 1이 코드 블록으로 보이며 이어서 첫 청크 원문이 들어 있다.](/images/ml-platform-engineering/sop/ch12-langfuse-generation.png)

   모델이 실제로 받은 프롬프트다. "검색 결과가 프롬프트에 그대로 들어갔는가"(문맥 구성 오류인가)는 여기서 본다. `**Documentation Context:**`가 코드 블록으로 보이는 것은 [문맥 구성](#augmentation-grounding)에서 설명한 f-string 들여쓰기 때문이다. Gemini에서는 시스템 지시를 사람 메시지로 바꾸는 `convert_system_message_to_human=True`가 필요했지만, 이 코드는 처음부터 프롬프트 전체를 사용자 메시지 하나로 보내므로 Ollama에서도 구조가 같다.
2. 트리의 1,854 tokens는 입력과 출력을 합한 값이다. 단계별 시간, 첫 토큰 시간, 토큰 수를 한 번에 보려면 Langfuse가 저장하는 ClickHouse 표를 직접 조회한다. Langfuse v4는 예전 `GET /api/public/traces` 대신 이 이벤트 표를 쓴다. 아래는 E-2, E-3의 두 trace다(출력 앞 6줄).
   ```powershell
   docker exec ch12-langfuse-clickhouse-1 clickhouse-client --user clickhouse --password clickhouse -q "SELECT substring(trace_id,1,8), name, round(dateDiff('millisecond', start_time, end_time)/1000,2) sec, round(dateDiff('millisecond', start_time, completion_start_time)/1000,2) ttft, usage_details FROM events_core WHERE start_time > '2026-11-08 01:05:00' ORDER BY start_time FORMAT PrettyCompact"
   ```
   ```text
       ┌─substring(trace_id, 1, 8)─┬─name──────────────────┬───sec─┬──ttft─┬─usage_details────────────────────────────┐
    1. │ 581073be                  │ dakkabot-query-stream │ 57.27 │  ᴺᵁᴸᴸ │ {}                                       │
    2. │ 581073be                  │ VectorStoreRetriever  │  0.06 │  ᴺᵁᴸᴸ │ {}                                       │
    3. │ 581073be                  │ ChatOllama            │ 57.21 │   0.2 │ {'input':1244,'output':610,'total':1854} │
    4. │ 2ed557d5                  │ dakkabot-query-stream │ 13.04 │  ᴺᵁᴸᴸ │ {}                                       │
    5. │ 2ed557d5                  │ VectorStoreRetriever  │  0.05 │  ᴺᵁᴸᴸ │ {}                                       │
    6. │ 2ed557d5                  │ ChatOllama            │ 12.99 │  0.26 │ {'input':665,'output':155,'total':820}   │
   ```
   시간대는 UTC다. 범위 밖 질문(665토큰)은 문서 질문(1,244토큰)보다 입력이 짧은데, 짧은 청크들이 검색됐기 때문이다. 첫 토큰 시간(`ttft`)이 0.2초대로 나온 것은 같은 프롬프트를 직전에 처리한 Ollama가 앞부분 계산을 재사용했기 때문으로 보이며, 처음 받는 질문의 대기 시간으로 읽으면 안 된다.

### F-4. 토큰과 비용 {#ch12-f-4}

1. 왼쪽 메뉴 Home을 연다.

   ![Langfuse Home. Traces 6개(dakkabot-query-stream 4, dakkabot-query 2), Model costs $0.00, llama3.2 7.76K tokens $0, Observations 18개.](/images/ml-platform-engineering/sop/ch12-langfuse-home.png)

   책의 그림 12.8은 Gemini 호출이라 비용이 달러로 쌓이지만, 여기서는 `llama3.2`의 단가가 없어 토큰 7.76K에 $0이다. 로컬 모델에도 비교용 비용을 보고 싶다면 Settings의 Models에서 모델 이름과 토큰 단가를 직접 등록한다. 이번 실습에서는 등록하지 않았다.

### F-5. 모델만 바꿔 생성 오류 만들기 {#ch12-f-5}

1. Chainlit을 멈추지 않고 다른 터미널에서, 모델만 `gemma3:270m`으로 바꿔 같은 질문을 보낸다. `load_dotenv`는 이미 있는 환경 변수를 덮어쓰지 않으므로 터미널에서 지정한 값이 이긴다.
   ```powershell
   cd ch12\dakkabot
   $env:OLLAMA_MODEL = "gemma3:270m"
   ..\venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); from dakka_bot_core import dakka_bot_query; print(dakka_bot_query('How often should production API keys be rotated?'))"
   Remove-Item Env:OLLAMA_MODEL
   ```
   ````text
   ```json
   {
     "activities": [
       {
         "activity_id": "string",
         "user_id": "string",
         "activity_type": "api_call",
   ...
   ````
   `llama3.2`는 같은 질문에 "every 90 days"라고 답했다. 두 trace의 `VectorStoreRetriever` 출력은 같고 generation 출력만 다르다. 검색은 맞고 생성이 틀린 경우가 trace에서 이렇게 보인다. 결과 비교는 [생성](#generation)의 표에 정리했다.

완료 기준: 한 trace에서 검색 span과 generation을 열어, E-2 답의 각 부분이 어느 청크에서 왔는지 또는 어디에도 없는지 말할 수 있다.

## G. 문제 해결과 정리 {#ch12-g}

### G-1. 자주 만나는 실패 {#ch12-g-1}

| 증상 | 위치 | 원인과 조치 |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'tqdm'` | `index.py` | 저자 `requirements.txt`에 없다. `uv pip install tqdm` |
| `ModuleNotFoundError: No module named 'guardrails'` | Chainlit 시작 | `guardrail_helpers` import. B-3처럼 13장 전까지 import하지 않는다 |
| 스크립트로는 trace가 남는데 Chainlit에서만 안 남음 | Langfuse | `guardrail_helpers`가 `OTEL_SDK_DISABLED=true`를 설정했다. B-3 |
| trace에 `ChatOllama`만 있고 검색이 없음 | Langfuse | retriever에 콜백을 넘기지 않았다. B-2 |
| `Failed to detach context`, 스트리밍 trace가 늦게 또는 오류와 함께 도착 | Chainlit 터미널 | span이 `done` 뒤까지 열려 있다. B-2 |
| `Failed to export spans batch due to timeout` | Python 터미널 | Langfuse가 꺼져 있다. 답은 정상으로 나오고 기록만 빠진다. D-2 |
| `docker compose up`에서 포트 할당 실패 | Langfuse | 9000(ClickHouse), 6379(Redis), 5432(Postgres)가 이미 쓰인다. D-1의 override |
| `GET /api/public/traces`가 "events_only mode" 오류 | Langfuse API | v4는 예전 조회 API를 막았다. 화면이나 ClickHouse로 본다 |
| 답이 엉뚱한 문서를 근거로 함, 오류 없음 | 검색 | 인덱스를 만든 임베딩과 검색 임베딩이 다르다. 차원이 같으면 오류가 안 난다. 인덱스를 다시 만든다 |
| 긴 문맥에서 답이 앞부분 지시를 무시함 | Ollama | `num_ctx`보다 긴 프롬프트가 잘렸다. `OLLAMA_NUM_CTX` 확인 |
| Gemini로 바꾸자 인덱싱에서 모델 없음 오류 | Gemini | `text-embedding-004` 종료. `GEMINI_EMBED_MODEL` 지정. 이번 실습에서는 키가 없어 실행하지 않았다 |

이번 실행에서 실제로 만난 것은 `tqdm`, Chainlit에서만 trace가 없던 문제, 검색 없는 trace, `Failed to detach context`, Langfuse가 꺼졌을 때의 export 오류, `events_only mode` 응답이다. 포트 충돌은 실행 전에 열린 포트를 확인하고 override로 피했고, 임베딩 불일치, `num_ctx` 잘림, Gemini 오류는 코드와 문서를 읽고 판단한 것이다.

### G-2. 정리 {#ch12-g-2}

1. Chainlit 터미널을 `Ctrl+C`로 멈춘다.
2. Langfuse를 멈춘다. `stop`은 데이터를 남기고, `down -v`는 컨테이너와 볼륨(trace)을 지운다.
   ```powershell
   cd ch12\langfuse
   docker compose -p ch12-langfuse stop
   ```
3. 13장은 이 DakkaBot과 Langfuse를 그대로 쓴다. 다시 켤 때는 D-2의 `docker compose -p ch12-langfuse up -d langfuse-web langfuse-worker`와 E-1의 `chainlit run`을 실행한다. 메모리에 올라간 Ollama 모델은 몇 분 뒤 자동으로 내려가고, 바로 내리려면 `ollama stop llama3.2`를 실행한다.
4. 완전히 지우려면 아래를 실행한다. `llama3.2`를 다른 곳에서 쓰지 않는다면 함께 지운다.
   ```powershell
   docker compose -p ch12-langfuse down -v
   docker image rm docker.langfuse.com/langfuse/langfuse:4.76.0 docker.langfuse.com/langfuse/langfuse-worker:4.76.0 clickhouse/clickhouse-server:26.3.62.3 cgr.dev/chainguard/minio:latest redis:7
   ollama rm nomic-embed-text
   ```

## 마치며 {#closing}

DakkaBot을 직접 돌려 보면 "RAG가 환각을 줄인다"는 말의 조건이 보인다. 답에 출처 다섯 개가 붙어 있어도 가장 가까운 청크는 테스트 코드였고, 다른 절차가 섞였고, 문서에 없는 YAML이 들어갔다. 범위 밖 질문에도 출처는 붙었고 거절 여부는 실행마다 달랐다. 이것을 구분할 수 있었던 것은 검색, 문맥 구성, 생성을 나눠 두고 그 사이의 입출력을 trace로 남겼기 때문이다. 모델을 Gemini에서 로컬 모델로 바꿔도 구조가 그대로였다는 점은 이 분리가 제공자 교체에도 쓸모 있다는 증거다. 13장은 여기서 본 실패를 질문 집합으로 모아 프롬프트를 버전 관리하고 시험하며, 가드레일과 비용 관리를 더한다.

[이전: 11. 모니터링과 설명가능성](../11-monitoring-and-explainability/), [시리즈 목차](../), [다음: 13. 프로덕션 LLM 시스템](../13-production-llm-systems/)
