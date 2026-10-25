---
title: "Prometheus, Grafana, Loki, Alertmanager: 장애를 대응으로 연결"
description: "Bookway의 서비스 상태, 로그, 품질 신호를 분리하고 실행 가능한 알림을 구성"
date: 2026-10-25T08:43:00+09:00
weight: 80
tags: ["mlops", "monitoring", "prometheus", "grafana"]
---

계기판이 위험을 보여 줘도 운전자가 무엇을 할지 모르면 사고를 막지 못합니다. Prometheus는 수치를 모으고 규칙을 평가하며, Grafana는 조회, 시각화, Loki는 로그 탐색, Alertmanager는 알림의 그룹화, 억제, 전달을 맡습니다.

## Bookway의 세 종류 신호

서비스는 요청 수, 오류율, 지연, 피처는 누락률, 공급 지연, 모델은 추천 노출 이후의 클릭, 구매, 품질을 봅니다. 마지막 신호는 정답 도착이 늦고 편향도 있으므로 HTTP 200과 같은 시간 창에서 단정하지 않습니다.

```text
추천 API metrics → Prometheus 규칙 → Alertmanager → 담당자, runbook
추천 API logs   → Loki             → trace / release로 원인 탐색
Prometheus, Loki → Grafana          → 같은 기간, 배포 표시 비교
```

## 메트릭 계약과 질의

앱이 `bookway_requests_total{route,status_class}`와 classic histogram `bookway_request_duration_seconds`를 노출한다고 가정합니다. 요청별 duration을 초 단위로 관측하고, 모든 인스턴스에 같은 bucket을 사용합니다.

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(bookway_request_duration_seconds_bucket[5m]))
)
```

이 값은 최근 창의 전체 서비스 p95 추정치입니다. Pod별 p95를 평균하면 같은 의미가 아닙니다. native histogram은 질의 형식이 다르므로 서버, 계측 라이브러리 지원을 맞춥니다.

```promql
sum(rate(bookway_requests_total{status_class="5xx"}[5m]))
/
clamp_min(sum(rate(bookway_requests_total[5m])), 0.001)
```

낮은 트래픽에서 비율만 보면 한 건의 오류가 과대 해석될 수 있어 최소 요청량과 지속 시간도 조건에 둡니다. bucket, label, 기록 규칙을 대시보드와 함께 버전 관리합니다.

## 로그와 알림의 실행 계약

고객 ID, 주문 ID, 질문 원문을 메트릭 label로 넣지 않습니다. cardinality와 개인정보 문제가 동시에 생깁니다. release, route, 모델 계열처럼 제한된 차원은 메트릭에, 개별 trace ID는 접근 통제된 로그나 exemplar에 연결합니다.

| 알림 | 첫 조사 | 대응 |
| --- | --- | --- |
| API 5xx 증가 | release별 오류, 의존성 | 새 배포 중단, 이전 정상 release 검토 |
| Feast missing 급증 | 공급 작업, schema, event 지연 | 원천 복구, 승인된 cold-start 정책 |
| 지연 증가 | 큐, 후보 수, CPU/GPU | 유입 제한, 병목 단계 조절 |
| 추천 반응 하락 | 노출 집합, 실험 배정, 정답 지연 | 데이터/모델 평가, 즉시 재학습 아님 |

Alertmanager에는 소유 팀, 우선순위, runbook, 복구 조건을 넣습니다. 상위 저장소 장애로 여러 API가 동시에 실패하면 알림을 묶고 종속 알림을 억제합니다.

LLMOps도 같은 기반을 사용하지만 TTFT, 전체 생성 시간, 토큰, 도구 오류, 평가 score를 추가합니다. 문장 내용은 [Langfuse](../../llmops/langfuse/) 같은 별도 제한 경로로 관리하고 [OTel](../../llmops/opentelemetry/) trace와 연결합니다.

[Prometheus histogram 문서](https://prometheus.io/docs/practices/histograms/) / [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) / [MLOps 전체 지도](../)
