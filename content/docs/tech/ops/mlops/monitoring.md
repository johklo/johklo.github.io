---
title: "Prometheus, Grafana, Loki, Alertmanager: 장애를 대응으로 연결"
description: "Bookway의 서비스 상태, 로그, 품질 신호를 분리하고 실행 가능한 알림을 구성"
date: 2026-10-25T08:43:00+09:00
weight: 80
tags: ["mlops", "monitoring", "prometheus", "grafana"]
aliases:
  - "/docs/tech/mlops/monitoring/"
---

Prometheus는 메트릭, 규칙, Grafana는 시각화, Loki는 로그, Alertmanager는 알림 그룹화, 억제, 전달을 맡는다.

## Bookway의 세 종류 신호

서비스는 요청, 오류, 지연, 피처는 누락, 공급 지연, 모델은 노출 후 클릭, 구매, 품질을 본다. 정답 지연과 편향 때문에 HTTP 200과 같은 창에서 단정하지 않는다.

```text
추천 API metrics → Prometheus 규칙 → Alertmanager → 담당자, runbook
추천 API logs   → Loki             → trace / release로 원인 탐색
Prometheus, Loki → Grafana          → 같은 기간, 배포 표시 비교
```

## 메트릭 계약과 질의

앱은 `bookway_requests_total{route,status_class}`와 classic histogram `bookway_request_duration_seconds`를 노출한다. duration은 초 단위, bucket은 인스턴스 간 동일하다고 가정한다.

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(bookway_request_duration_seconds_bucket[5m]))
)
```

값은 최근 창의 전체 p95 추정치다. Pod별 p95 평균과는 다르며 native histogram은 서버, 계측 라이브러리별 질의를 확인한다.

```promql
sum(rate(bookway_requests_total{status_class="5xx"}[5m]))
/
clamp_min(sum(rate(bookway_requests_total[5m])), 0.001)
```

저트래픽에서는 한 오류가 비율을 왜곡하므로 최소 요청량, 지속 시간도 조건에 둔다. bucket, label, 규칙을 대시보드와 버전 관리한다.

## 로그와 알림의 실행 계약

고객, 주문 ID와 질문 원문은 cardinality, 개인정보 위험 때문에 metric label에서 제외한다. 제한된 release, route, 모델 label만 쓰고 trace ID는 통제된 로그에 둔다.

| 알림 | 첫 조사 | 대응 |
| --- | --- | --- |
| API 5xx 증가 | release별 오류, 의존성 | 새 배포 중단, 이전 정상 release 검토 |
| Feast missing 급증 | 공급 작업, schema, event 지연 | 원천 복구, 승인된 cold-start 정책 |
| 지연 증가 | 큐, 후보 수, CPU/GPU | 유입 제한, 병목 단계 조절 |
| 추천 반응 하락 | 노출 집합, 실험 배정, 정답 지연 | 데이터/모델 평가, 즉시 재학습 아님 |

Alertmanager에는 소유 팀, 우선순위, runbook, 복구 조건을 넣는다. 상위 저장소 장애로 여러 API가 동시에 실패하면 알림을 묶고 종속 알림을 억제한다.

LLMOps도 같은 기반을 사용하지만 TTFT, 전체 생성 시간, 토큰, 도구 오류, 평가 score를 추가한다. 문장 내용은 [Langfuse](/docs/tech/ops/llmops/langfuse/) 같은 별도 제한 경로로 관리하고 [OTel](/docs/tech/ops/llmops/opentelemetry/) trace와 연결한다.

[Prometheus histogram 문서](https://prometheus.io/docs/practices/histograms/) / [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) / [MLOps 전체 지도](/docs/tech/ops/mlops/)
