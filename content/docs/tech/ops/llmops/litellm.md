---
title: "LiteLLM: 모델 접속, 라우팅, 예산의 공통 창구"
description: "Bookway의 모델 alias와 공급자 장애, 비용, 권한 정책을 앱에서 분리"
date: 2026-10-25T08:43:00+09:00
weight: 80
tags: ["llmops", "litellm", "gateway"]
aliases:
  - "/docs/tech/llmops/litellm/"
---

LiteLLM Proxy는 모델 공급자 앞의 공통 호출 창구다. OpenAI-compatible 인터페이스, 라우팅, 사용량, 인증, 예산 기능을 제공하지만 모델 가중치를 로딩하는 [vLLM](/docs/tech/ops/llmops/vllm/)과는 다르다.

## Bookway의 접속 구조

```text
도우미 앱
  → 프로젝트별 gateway key
  → LiteLLM alias bookway-chat
  → 승인된 관리형 deployment 또는 vLLM
  → 실제 모델, 토큰, 시간, 오류 기록
```

앱은 alias를 쓰더라도 release와 trace에는 실제로 호출한 deployment, model revision을 기록한다. alias가 같아도 tool calling, JSON, 문맥 길이, 안전 설정이 같다는 뜻은 아니다.

## 로컬 연결 예시

`litellm[proxy]`가 설치되고 Ollama에 `llama3.2:latest`가 준비된 개발 환경의 `gateway.yaml`이다. loopback 전용이며 운영 인증, DB 설정을 생략한 연결 확인용 구성이다.

```yaml
model_list:
  - model_name: bookway-chat
    litellm_params:
      model: ollama_chat/llama3.2:latest
      api_base: http://127.0.0.1:11434
```

```powershell
litellm --config gateway.yaml --host 127.0.0.1 --port 4000
```

앱은 `http://127.0.0.1:4000/v1`의 chat completion 경로를 사용한다. 이 주소를 그대로 외부에 노출하지 않는다. 운영은 master key, 가상 key, 허용 모델, TLS, DB, 네트워크를 구성하고 비밀값을 YAML 대신 secret에서 주입한다.

## fallback과 재시도

정책 질의의 일반 생성과 환불 도구 인자 생성은 다른 위험을 가진다. 저렴한 모델로 fallback할 때 schema, 언어, 도구 품질이 달라지므로 동일 평가집을 통과한 조합만 허용한다. 아무 모델이나 자동 대체하는 것은 가용성 개선처럼 보여도 업무 회귀가 될 수 있다.

앱, gateway, provider SDK가 각각 재시도하면 호출 수가 곱으로 늘어난다. 전체 deadline과 총 시도 한도를 정하고 429, timeout, 잘못된 요청을 구분한다. 응답 유실 후 도구 실행을 재시도할 때에는 별도 업무 멱등 키가 필요하다.

## 비용과 운영 경계

팀, 환경, 용도별 key를 나누고 token, 비용, 호출률을 기록한다. 예산 추적과 강제 차단이 어떤 저장소, 배포 옵션에서 보장되는지 확인한다. 동시 요청, 스트리밍, 사후 정산 때문에 단순 budget 표시가 엄격한 청구 상한과 같지 않을 수 있다.

원문 logging, callback이 켜지는 범위를 검토하고 외부 관측 서비스로 고객 내용을 복제하지 않는다. gateway 장애 시 앱이 공급자에 무조건 직접 우회하면 인증, 예산, 감사를 모두 우회할 수 있으므로 승인된 비상 경로만 둔다.

[공식 Proxy 시작](https://docs.litellm.ai/docs/proxy/quick_start) / [vLLM 역할](/docs/tech/ops/llmops/vllm/) / [release의 모델 계약](/docs/tech/ops/llmops/release/)
