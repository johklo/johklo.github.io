---
title: "12. 다중 에이전트"
description: "여행 정보와 숙박 도구를 나누고 Router와 Supervisor로 요청을 위임하는 구조"
date: 2026-10-19T21:37:00+09:00
weight: 120
tags: ["book-club", "ai-agents-and-applications", "langgraph", "multi-agent"]
---

안내 직원이 갈 만한 마을을 골라 주고 숙박 직원이 그 마을의 방을 찾는다고 생각해 보겠습니다. 두 사람이 각각 일을 잘해도 서로 다른 마을을 기준으로 답하면 요청은 실패입니다. 여러 에이전트에서 중요한 것은 역할 이름보다 **앞의 결과를 다음 작업에 정확히 전달하는 계약**입니다.

## 12.1 숙박 에이전트

여행 정보 에이전트는 장소와 날씨를 다루고, 숙박 에이전트는 호텔과 B&B의 가용 객실 및 제안을 조회합니다. 정보와 도구의 책임을 나누는 구조입니다.

### 12.1.1 호텔 도구

책은 SQLite에 저장된 호텔 자료를 SQL 도구로 제공합니다. 모델이 스키마를 확인하고 필요한 조회를 실행할 수 있도록 도구 집합을 연결합니다.

일반적인 SQL toolkit은 단일 “호텔 조회” 함수보다 넓은 기능을 노출할 수 있습니다. 어떤 테이블과 명령이 허용되는지 확인하고 읽기 전용 권한과 실행 제한을 적용해야 합니다.

현재 객실과 가격은 변경되는 데이터입니다. 결과에는 대상 날짜와 객실 수, 통화와 가격 기준을 포함해야 합니다. 질문에 날짜가 없다면 임의로 정하기보다 확인이 필요할 수 있습니다.

### 12.1.2 B&B 도구

다른 제공자의 REST 서비스를 모의 구현으로 연결합니다. 장소와 객실 수 등을 받아 제안 목록을 반환합니다.

SQL 행과 API 응답을 같은 의미로 비교하려면 필드와 단위를 맞춰야 합니다. 1박 가격과 전체 숙박 가격, 객실 수와 인원 수를 섞으면 자연스러운 답변도 틀릴 수 있습니다.

빈 결과와 오류도 구분해야 합니다. 객실이 없는 것과 외부 API가 응답하지 않은 것은 다른 상황입니다.

### 12.1.3 ReAct 숙박 에이전트

호텔과 B&B 도구를 함께 제공해 조건에 맞는 결과를 모으도록 합니다. 숙소 유형을 정하지 않았다면 둘 다 확인하는 정책을 둘 수 있습니다.

책의 booking이라는 이름에도 실제 예제의 핵심은 가용 객실과 제안 조회입니다. 목록을 확인하는 기능과 객실을 확보하거나 결제를 실행하는 기능을 같은 것으로 보면 안 됩니다.

실제 예약을 추가하면 사용자 확인, 재고 재검증, 중복 방지와 취소 절차가 필요합니다. 조회 시점에 있던 객실이 예약 시점에도 있다는 보장은 없습니다.

## 12.2 Router 기반 여행 도우미

질문을 보고 여행 정보 또는 숙박 에이전트로 한 번 위임합니다. 각 전문 에이전트의 도구와 프롬프트는 독립적으로 관리할 수 있습니다.

### 12.2.1 라우터 설계

라우터는 사용 가능한 에이전트의 이름과 처리 범위를 알아야 합니다. 자유 문자열보다 허용 이름을 가진 구조화된 출력으로 경로를 제한하는 편이 명확합니다.

모든 질문이 둘 중 하나에 속하지는 않습니다. 범위 밖 요청이나 불명확한 입력을 어떻게 처리할지도 정해야 합니다.

### 12.2.2 라우팅 로직

질문을 분류하고 `Command` 같은 실행 제어 객체로 대상 노드와 필요한 상태 갱신을 지정할 수 있습니다.

에이전트 이름을 고르는 것과 업무가 성공하는 것은 다릅니다. 라우터가 올바른 이름을 반환해도 전달한 질문에서 날짜나 객실 수를 잃었다면 결과가 달라집니다.

상태를 그대로 넘기는 경우에도 다른 에이전트가 읽어도 되는 정보인지 확인해야 합니다. 메시지 전체를 공유하는 방식은 간단하지만 불필요한 문맥과 민감한 정보가 넓게 퍼질 수 있습니다.

### 12.2.3 그래프 구성

상위 경로는 Router에서 전문 에이전트로 이동하고, 전문 에이전트 내부에서는 도구 루프가 돌아갑니다. 바깥은 제한된 경로 선택이고 안쪽은 모델이 여러 도구를 선택하는 혼합 구조입니다.

하위 에이전트가 끝났을 때 사용자 응답으로 종료할지 상위로 돌아올지가 중요한 차입니다. Router 구조에서는 보통 선택된 한 경로에서 요청을 마칩니다.

### 12.2.4 실행 확인

관광지 질문과 빈 객실 질문을 각각 넣어 어느 경로가 선택되는지 확인합니다. 이름 분류뿐 아니라 적절한 도구를 사용했는지도 봐야 합니다.

“날씨가 좋은 해안 마을을 고르고 그곳의 숙소도 찾아 달라”는 요청은 두 업무를 포함합니다. 한 경로로만 보내는 구조에서는 일부 요구를 놓칠 수 있습니다.

## 12.3 Supervisor

Supervisor는 전문 에이전트를 작업 도구처럼 호출하고 결과를 받은 뒤 다음 작업을 결정합니다. 단순히 한 번 분류하는 Router보다 조정의 범위가 넓습니다.

### 12.3.1 에이전트를 조정하는 에이전트

전문 에이전트마다 역할과 입력, 결과 형식을 명확히 해야 합니다. Supervisor는 어떤 능력이 있고 어떤 경우에 호출해야 하는지 설명을 보고 위임합니다.

이름이 다른 모델 여러 개보다 업무 경계가 중요합니다. 같은 모델을 사용해도 서로 다른 도구와 지침, 상태 범위를 가지면 역할을 분리할 수 있습니다.

### 12.3.2 결과 회수와 재위임

![Supervisor가 여행 정보 에이전트와 숙박 에이전트를 호출하고 결과를 돌려받는 구조. 각 전문 에이전트는 자체 검색 및 날씨, 호텔과 B&B 도구를 사용합니다.](/images/ai-agents-and-applications/figure-12-03.png "그림 12.3. Supervisor 기반 여행 도우미. 출처: AI Agents and Applications, 12장.")

그림의 핵심은 전문 에이전트에서 Supervisor로 돌아오는 경로입니다. 여행 정보에서 정한 마을을 받은 뒤 그 마을의 숙소를 조회할 수 있습니다. 한 번의 요청 안에서도 같은 전문 에이전트를 다시 호출할 수 있습니다.

그러나 위임이 많을수록 지연과 비용, 정보 손실이 늘어납니다. 전문 에이전트가 원문 근거 대신 짧은 결론만 반환하면 Supervisor가 잘못된 판단을 조사하기 어렵습니다. 필요한 사실과 출처, 실패 상태를 구조화해서 반환하는 편이 좋습니다.

| 구분 | Router | Supervisor |
| --- | --- | --- |
| 주된 판단 | 누가 이 요청을 처리할지 | 어떤 작업을 어떤 순서로 맡길지 |
| 결과 경로 | 전문 에이전트가 응답하고 종료 가능 | 결과를 받아 추가 위임과 통합 |
| 적합한 요청 | 분리된 단일 업무 | 여러 역할의 결과가 필요한 업무 |
| 주요 부담 | 오분류와 복합 요청 누락 | 반복 위임, 비용, 상태 전달 |

### 12.3.3 복합 요청 실행

“해안 마을을 찾고 현재 날씨를 확인한 뒤 객실을 조회”한다면 장소 선정이 먼저입니다. 숙박 도구가 실행됐다고 전체 성공이 아니라, 선정된 장소와 실제 조회한 장소가 같은지까지 확인해야 합니다.

결과에는 어떤 조건을 충족했고 어느 항목을 확인하지 못했는지 남깁니다. 외부 서비스 하나가 실패한 경우 다른 에이전트의 성공 결과를 마치 모든 확인이 끝난 것처럼 표현하면 안 됩니다.

종료 기준과 위임 한도가 필요합니다. Supervisor가 더 나은 결과를 찾겠다고 같은 에이전트를 계속 호출할 수 있으므로 요청별 시간과 비용, 반복 횟수를 통제합니다.

## 여러 에이전트가 필요한지 판단하기

업무와 도구를 분리하면 프롬프트 길이와 권한 범위를 줄이고 부분별 평가가 쉬워질 수 있습니다. 반대로 단순 작업을 인위적으로 여러 에이전트로 나누면 전달과 재해석의 비용만 늘 수 있습니다.

한 에이전트와 몇 개의 명시적 도구로 충분한지부터 비교해야 합니다. 에이전트 수가 시스템의 성숙도를 나타내는 것은 아닙니다.

## 직접 해보기: 고른 장소를 숙박 담당자에게 그대로 전달하기

`ch12.py`로 저장합니다. 두 역할이 같은 로컬 모델을 쓰되, 읽는 자료와 내보내는 스키마를 분리했습니다. 조정자는 상태를 보고 다음 역할을 선택하는 코드입니다. 모델이 자유롭게 위임 순서를 정하는 Supervisor로 확장하기 전에, 결과 회수와 전달부터 확인한 구성입니다.

```python
from typing import Literal, TypedDict
from pydantic import BaseModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

class Destination(BaseModel):
    town: Literal["Falmouth"]

class HotelChoice(BaseModel):
    hotel: Literal["Harbour"]

class State(TypedDict):
    request: str
    town: str
    hotel: str
    visited: list[str]

model = ChatOllama(
    model="llama3.2:latest", temperature=0, format="json", num_predict=100,
)

def travel(state):
    prompt = ChatPromptTemplate.from_template(
        'Choose from this study catalogue: Falmouth has a railway station. '
        'Return JSON {{"town": "Falmouth"}} for this request: {request}'
    )
    choice = Destination.model_validate((
        prompt | model | JsonOutputParser()
    ).invoke({"request": state["request"]}))
    return {"town": choice.town, "visited": state["visited"] + ["travel"]}

def accommodation(state):
    if state["town"] != "Falmouth":
        raise ValueError("No study hotel catalogue for this destination")
    prompt = ChatPromptTemplate.from_template(
        'Study catalogue for {town}: Harbour costs 80 pounds per night. '
        'Return JSON {{"hotel": "Harbour"}} for a suitable offer. Request: {request}'
    )
    choice = HotelChoice.model_validate((
        prompt | model | JsonOutputParser()
    ).invoke({"town": state["town"], "request": state["request"]}))
    return {"hotel": choice.hotel, "visited": state["visited"] + ["accommodation"]}

def route(state):
    if not state["town"]:
        return "travel"
    return "accommodation" if not state["hotel"] else "done"

builder = StateGraph(State)
builder.add_node("supervisor", lambda state: {})
builder.add_node("travel", travel)
builder.add_node("accommodation", accommodation)
builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", route, {
    "travel": "travel", "accommodation": "accommodation", "done": END,
})
builder.add_edge("travel", "supervisor")
builder.add_edge("accommodation", "supervisor")
result = builder.compile().invoke({
    "request": "Find a study town reachable by train and a hotel under 100 pounds.",
    "town": "", "hotel": "", "visited": [],
}, config={"recursion_limit": 10})
print(result)
assert result["visited"] == ["travel", "accommodation"]
assert (result["town"], result["hotel"]) == ("Falmouth", "Harbour")
```

```powershell
python ch12.py
```

각 역할이 끝난 뒤 조정자로 돌아오므로 숙박 담당자는 실제로 선택된 `town`을 받습니다. 두 역할을 동시에 실행했다면 숙박 쪽에는 아직 장소가 없습니다. 이 예제의 순서는 병렬 처리 대상이 아니라 **데이터 의존성**입니다.

선택지가 하나라 모델의 선택 능력을 평가하는 예제는 아닙니다. 먼저 위임·회수·자료형 계약을 작게 확인했습니다. 다음에는 두 마을과 서로 다른 가격을 넣고, 잘못된 장소나 예산 초과 결과가 나오는지 평가할 수 있습니다.

직접 확인할 질문: “숙박 담당자가 답했으니 예약도 끝났을까요?” 이 프로그램은 안내를 골랐을 뿐입니다. 재고 확보나 결제 도구를 호출하지 않았으므로 예약 완료라고 표시하면 안 됩니다.

실패 실험: `accommodation()`에 `town="Truro"`를 전달하면 임의의 숙소를 대신 고르지 않고 중단됩니다. 담당 범위 밖 요청을 성공처럼 채우지 않는 것이 역할 분리의 중요한 조건입니다.

한 줄 정리: 다중 에이전트는 **역할별 지침보다 결과의 회수·전달·검증 경계**부터 설계합니다.

## 질문

### Router도 여러 작업을 해결할 수 있을까?

별도의 분해와 반복 경로를 구현하면 가능합니다. 이 장에서 비교하는 단순 Router는 한 번의 선택으로 끝나는 구조라 복합 요청에서 한계가 드러납니다.

### 숙소를 조회했으면 예약까지 완료된 것일까?

조회와 실제 거래는 다른 작업입니다. 예약 확정 결과가 없으면 완료라고 답해서는 안 됩니다.

[이전: 도구 기반 에이전트](../11-tool-agents/) / [시리즈 목차](../) / [다음: MCP 서버](../13-mcp-servers/)
