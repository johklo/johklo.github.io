---
title: "12. 다중 에이전트"
description: "여행 정보와 숙박 도구를 나누고 Router와 Supervisor로 요청을 위임하는 구조"
date: 2026-10-19T21:37:00+09:00
weight: 120
tags: ["book-club", "ai-agents-and-applications", "langgraph", "multi-agent"]
---

한 에이전트가 여행지를 고르고 다른 에이전트가 숙소를 찾는다면, 숙소 검색은 선택된 여행지를 받아야 시작할 수 있다. 역할 이름을 늘리는 것보다 **앞의 결과가 다음 작업에 제대로 전달되는지**가 중요해서, 이 장은 역할 분담과 데이터 의존성을 함께 정리했다.

## 12.1 숙박 에이전트

여행 정보 에이전트는 장소와 날씨를 다루고, 숙박 에이전트는 호텔과 B&B의 가용 객실 및 제안을 조회한다. 정보와 도구의 책임을 나누는 구조이다.

### 12.1.1 호텔 도구

책은 SQLite에 저장된 호텔 자료를 SQL 도구로 제공한다. 모델이 스키마를 확인하고 필요한 조회를 실행할 수 있도록 도구 집합을 연결한다.

일반적인 SQL toolkit은 단일 “호텔 조회” 함수보다 넓은 기능을 노출할 수 있다. 어떤 테이블과 명령이 허용되는지 확인하고 읽기 전용 권한과 실행 제한을 적용해야 한다.

현재 객실과 가격은 변경되는 데이터이다. 결과에는 대상 날짜와 객실 수, 통화와 가격 기준을 포함해야 한다. 질문에 날짜가 없다면 임의로 정하기보다 확인이 필요할 수 있다.

### 12.1.2 B&B 도구

다른 제공자의 REST 서비스를 모의 구현으로 연결한다. 장소와 객실 수 등을 받아 제안 목록을 반환한다.

SQL 행과 API 응답을 같은 의미로 비교하려면 필드와 단위를 맞춰야 한다. 1박 가격과 전체 숙박 가격, 객실 수와 인원 수를 섞으면 자연스러운 답변도 틀릴 수 있다.

빈 결과와 오류도 구분해야 한다. 객실이 없는 것과 외부 API가 응답하지 않은 것은 다른 상황이다.

### 12.1.3 ReAct 숙박 에이전트

호텔과 B&B 도구를 함께 제공해 조건에 맞는 결과를 모으도록 한다. 숙소 유형을 정하지 않았다면 둘 다 확인하는 정책을 둘 수 있다.

책의 booking이라는 이름에도 실제 예제의 핵심은 가용 객실과 제안 조회이다. 목록을 확인하는 기능과 객실을 확보하거나 결제를 실행하는 기능을 같은 것으로 보면 안 된다.

실제 예약을 추가하면 사용자 확인, 재고 재검증, 중복 방지와 취소 절차가 필요하다. 조회 시점에 있던 객실이 예약 시점에도 있다는 보장은 없다.

### 역할 분리보다 먼저 입력·결과 계약 만들기

여행 담당자가 “괜찮은 마을을 골랐어요”라고만 말하면 숙박 담당자는 조회를 시작할 수 없다. 전문 역할을 나누려면 대화를 멋지게 만드는 것보다 **다음 역할이 사용할 값**을 정해야 한다.

| 전달 방향 | 필요한 값의 예 | 전달하지 말아야 할 모호함 |
| --- | --- | --- |
| 사용자 → 조정자 | 지역, 교통 조건, 예산, 날짜 | 예산의 단위를 임의로 추정 |
| 여행 역할 → 조정자 | 선정한 장소 ID, 이름, 선택 근거, 미확인 조건 | “그 해안 마을”만 반환 |
| 조정자 → 숙박 역할 | 같은 장소, 날짜, 인원, 예산 단위 | 사용자의 필수 조건을 요약하며 삭제 |
| 숙박 역할 → 조정자 | 제안 ID, 가격, 통화, 단위, 조회 상태 | 조회 결과를 예약 확정으로 표현 |

모든 역할이 전체 대화와 모든 도구를 공유할 필요는 없다. 여행 역할에는 여행 근거를, 숙박 역할에는 필요한 장소와 숙박 조건을 주는 방식으로 범위를 줄일 수 있다. 다만 너무 짧은 결과만 회수하면 상위 조정자가 판단을 검토할 근거가 사라진다. 사실 값과 근거, 확인하지 못한 항목을 함께 반환하는 균형이 필요하다.

## 12.2 Router 기반 여행 도우미

질문을 보고 여행 정보 또는 숙박 에이전트로 한 번 위임한다. 각 전문 에이전트의 도구와 프롬프트는 독립적으로 관리할 수 있다.

![Router가 여행 정보 또는 숙박 에이전트를 선택하고 각 에이전트가 자체 도구를 사용한 뒤 종료하는 두 갈래 구조.](/images/ai-agents-and-applications/figure-12-01.png "그림 12.1. Router 기반 다중 에이전트 여행 도우미. 출처: AI Agents and Applications, 12장.")

이 그림은 전화를 알맞은 부서로 돌려주는 교환대처럼 읽을 수 있다. 전문 에이전트의 도구 결과는 해당 에이전트로 돌아오지만, 일을 마친 결과가 상위 Router로 돌아오는 경로는 없다. 뒤의 그림 12.3과 나란히 보면 **한 번 넘기기와 결과를 받아 다시 조정하기**의 차이가 보이다.

### 12.2.1 라우터 설계

라우터는 사용 가능한 에이전트의 이름과 처리 범위를 알아야 한다. 자유 문자열보다 허용 이름을 가진 구조화된 출력으로 경로를 제한하는 편이 명확하다.

모든 질문이 둘 중 하나에 속하지는 않는다. 범위 밖 요청이나 불명확한 입력을 어떻게 처리할지도 정해야 한다.

### 12.2.2 라우팅 로직

질문을 분류하고 `Command` 같은 실행 제어 객체로 대상 노드와 필요한 상태 갱신을 지정할 수 있다.

에이전트 이름을 고르는 것과 업무가 성공하는 것은 다르다. 라우터가 올바른 이름을 반환해도 전달한 질문에서 날짜나 객실 수를 잃었다면 결과가 달라진다.

상태를 그대로 넘기는 경우에도 다른 에이전트가 읽어도 되는 정보인지 확인해야 한다. 메시지 전체를 공유하는 방식은 간단하지만 불필요한 문맥과 민감한 정보가 넓게 퍼질 수 있다.

### 12.2.3 그래프 구성

상위 경로는 Router에서 전문 에이전트로 이동하고, 전문 에이전트 내부에서는 도구 루프가 돌아간다. 바깥은 제한된 경로 선택이고 안쪽은 모델이 여러 도구를 선택하는 혼합 구조이다.

하위 에이전트가 끝났을 때 사용자 응답으로 종료할지 상위로 돌아올지가 중요한 차이다. Router 구조에서는 보통 선택된 한 경로에서 요청을 마친다.

### 12.2.4 실행 확인

관광지 질문과 빈 객실 질문을 각각 넣어 어느 경로가 선택되는지 확인한다. 이름 분류뿐 아니라 적절한 도구를 사용했는지도 봐야 한다.

“날씨가 좋은 해안 마을을 고르고 그곳의 숙소도 찾아 달라”는 요청은 두 업무를 포함한다. 한 경로로만 보내는 구조에서는 일부 요구를 놓칠 수 있다.

## 12.3 Supervisor

Supervisor는 전문 에이전트를 작업 도구처럼 호출하고 결과를 받은 뒤 다음 작업을 결정한다. 단순히 한 번 분류하는 Router보다 조정의 범위가 넓다.

### 12.3.1 에이전트를 조정하는 에이전트

전문 에이전트마다 역할과 입력, 결과 형식을 명확히 해야 한다. Supervisor는 어떤 능력이 있고 어떤 경우에 호출해야 하는지 설명을 보고 위임한다.

이름이 다른 모델 여러 개보다 업무 경계가 중요하다. 같은 모델을 사용해도 서로 다른 도구와 지침, 상태 범위를 가지면 역할을 분리할 수 있다.

### 12.3.2 결과 회수와 재위임

![Supervisor가 여행 정보 에이전트와 숙박 에이전트를 호출하고 결과를 돌려받는 구조. 각 전문 에이전트는 자체 검색 및 날씨, 호텔과 B&B 도구를 사용한다.](/images/ai-agents-and-applications/figure-12-03.png "그림 12.3. Supervisor 기반 여행 도우미. 출처: AI Agents and Applications, 12장.")

그림의 핵심은 전문 에이전트에서 Supervisor로 돌아오는 경로이다. 여행 정보에서 정한 마을을 받은 뒤 그 마을의 숙소를 조회할 수 있다. 한 번의 요청 안에서도 같은 전문 에이전트를 다시 호출할 수 있다.

그러나 위임이 많을수록 지연과 비용, 정보 손실이 늘어난다. 전문 에이전트가 원문 근거 대신 짧은 결론만 반환하면 Supervisor가 잘못된 판단을 조사하기 어렵다. 필요한 사실과 출처, 실패 상태를 구조화해서 반환하는 편이 좋다.

| 구분 | Router | Supervisor |
| --- | --- | --- |
| 주된 판단 | 누가 이 요청을 처리할지 | 어떤 작업을 어떤 순서로 맡길지 |
| 결과 경로 | 전문 에이전트가 응답하고 종료 가능 | 결과를 받아 추가 위임과 통합 |
| 적합한 요청 | 분리된 단일 업무 | 여러 역할의 결과가 필요한 업무 |
| 주요 부담 | 오분류와 복합 요청 누락 | 반복 위임, 비용, 상태 전달 |

### 12.3.3 복합 요청 실행

“해안 마을을 찾고 현재 날씨를 확인한 뒤 객실을 조회”한다면 장소 선정이 먼저이다. 숙박 도구가 실행됐다고 전체 성공이 아니라, 선정된 장소와 실제 조회한 장소가 같은지까지 확인해야 한다.

결과에는 어떤 조건을 충족했고 어느 항목을 확인하지 못했는지 남긴다. 외부 서비스 하나가 실패한 경우 다른 에이전트의 성공 결과를 마치 모든 확인이 끝난 것처럼 표현하면 안 된다.

종료 기준과 위임 한도가 필요하다. Supervisor가 더 나은 결과를 찾겠다고 같은 에이전트를 계속 호출할 수 있으므로 요청별 시간과 비용, 반복 횟수를 통제한다.

### 복합 요청을 작업표로 풀어 보기

요청이 “기차로 갈 수 있는 마을과 100파운드 이하 숙소를 찾아 달라”라면, 마지막 답변을 쓰기 전에 충족해야 하는 조건이 두 개이다. 조정자의 상태를 다음처럼 읽을 수 있다.

```text
시작: 장소 없음, 숙소 없음
  → 여행 역할에 접근 가능한 장소 선정 요청
회수: 장소=Falmouth, 교통 근거 확보
  → 같은 장소와 예산을 숙박 역할에 전달
회수: 숙소=Harbour, 가격 조건 확인
  → 요구별 결과를 통합하고 종료
```

숙소가 없을 때는 두 정책이 가능하다. 선택한 장소를 유지하고 조건에 맞는 숙소가 없다고 답할 수도 있고, 사용자가 허용한 범위 안에서 다른 장소를 검토할 수도 있다. 후자를 선택한다면 장소 변경 뒤 숙박 결과를 다시 확인해야 한다. 예전 장소의 객실을 새 장소의 결과와 합치면 안 된다.

이런 상태 전이가 필요한 것이 Supervisor의 이유이다. 단순히 에이전트 두 개를 차례로 호출하는 것과, 회수한 결과를 보고 다음 위임을 바꾸는 것은 다르다. 업무 순서가 항상 같다면 모델이 조정하는 방식보다 코드가 정한 워크플로가 더 단순할 수도 있다.

### 일부 작업만 성공했을 때의 답변

여행 정보는 확보했지만 숙박 API가 실패했다고 가정해 보자. “숙소가 없다”는 결과와 “숙소를 확인하지 못했다”는 결과는 다르다. 전자는 조회에 성공한 빈 결과이고 후자는 시스템 실패이다.

조정자는 `found`, `no_match`, `unavailable`처럼 의미가 다른 상태를 보존해야 한다. 성공한 여행 결과를 유지하면서 숙박 확인 실패를 알릴 수 있지만, 모든 조건을 충족한 여행안을 찾았다고 표현해서는 안 된다. 여러 역할로 나눌수록 **전체 성공 기준을 누가 판단하는지**가 더 중요해진다.

## 여러 에이전트가 필요한지 판단하기

업무와 도구를 분리하면 프롬프트 길이와 권한 범위를 줄이고 부분별 평가가 쉬워질 수 있다. 반대로 단순 작업을 인위적으로 여러 에이전트로 나누면 전달과 재해석의 비용만 늘 수 있다.

한 에이전트와 몇 개의 명시적 도구로 충분한지부터 비교해야 한다. 에이전트 수가 시스템의 성숙도를 나타내는 것은 아니다.

### 하나의 에이전트와 비교할 때 볼 비용

다중 에이전트에서는 도구 호출 외에도 조정자와 역할별 모델 호출이 추가된다. 상위 요청을 해석하고, 각 역할이 자료를 읽고, 결과를 요약해 돌려주고, 조정자가 다시 통합하면서 같은 조건을 여러 번 해석할 수 있다.

역할 분리가 유리한지는 코드 줄 수보다 요구가 얼마나 다른지로 판단한다. 자료 접근 권한과 담당 팀, 도구 계약이 명확히 다르다면 분리의 이점이 크다. 같은 두 도구를 같은 권한으로 호출하는 짧은 작업이라면 하나의 에이전트나 명시적 순차 흐름이 더 이해하기 쉬울 수 있다.

평가는 역할별 정답과 전체 성공을 나눈다. 장소 선택이 맞고 숙소 조회도 성공했지만 두 장소가 다르면 전체 실패이다. 각 역할의 로컬 성공 표시만 합산하지 말고, 전달한 식별자와 조건이 끝까지 일치하는지 검사해야 한다.

## 실습: 여행 역할에서 숙박 역할로 장소 전달

`ch12.py`로 저장한다. 두 역할이 같은 로컬 모델을 쓰되, 읽는 자료와 내보내는 스키마를 분리했다. 조정자는 상태를 보고 다음 역할을 선택하는 코드이다. 모델이 자유롭게 위임 순서를 정하는 Supervisor로 확장하기 전에, 결과 회수와 전달부터 확인한 구성이다.

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

각 역할이 끝난 뒤 조정자로 돌아오므로 숙박 담당자는 실제로 선택된 `town`을 받는다. 두 역할을 동시에 실행했다면 숙박 쪽에는 아직 장소가 없다. 이 예제의 순서는 병렬 처리 대상이 아니라 **데이터 의존성**이다.

### 실습의 조정자는 무엇을 보고 움직이나요?

`supervisor` 노드 자체는 빈 갱신 사전을 반환하고, 그 뒤 `route()`가 상태를 읽어 다음 경로를 정한다. `town`이 비어 있으면 여행 역할, 장소는 있지만 `hotel`이 비어 있으면 숙박 역할, 둘 다 있으면 종료한다. 조정 결정을 LLM에게 맡기지 않았으므로 같은 상태에서는 같은 경로가 선택된다.

`visited`는 실제 역할 방문 순서를 기록한다. 마지막의 `["travel", "accommodation"]` 검사는 결과 문자열만 맞췄는지가 아니라 필요한 순서로 역할을 거쳤는지 확인한다. 두 모델 호출의 JSON 결과는 각각 `Destination`, `HotelChoice`로 검증한 뒤 상태에 반영된다.

이 구성은 책의 Supervisor 원리 중 위임, 회수, 다음 입력 전달을 작게 확인한다. 자율적인 조정 정책을 시험하려면 허용 역할과 `done` 같은 종료 선택을 모델에 제공하고, 잘못된 위임, 반복, 조기 종료를 별도로 평가해야 한다. 현재 예제의 성공을 그 평가까지 완료한 것으로 해석하지 않는다.

선택지가 하나라 모델의 선택 능력을 평가하는 예제는 아니다. 먼저 위임, 회수, 자료형 계약을 작게 확인했다. 다음에는 두 마을과 서로 다른 가격을 넣고, 잘못된 장소나 예산 초과 결과가 나오는지 평가할 수 있다.

숙박 담당자의 응답은 예약 완료를 뜻하지 않는다. 이 프로그램은 안내를 골랐을 뿐이며, 재고 확보나 결제 도구를 호출하지 않았다.

`accommodation()`에 `town="Truro"`가 전달되면 임의의 숙소를 대신 고르지 않고 중단된다. 담당 범위 밖 요청을 성공처럼 채우지 않는 것이 역할 분리의 중요한 조건이다.

다중 에이전트는 **역할별 지침보다 결과의 회수, 전달, 검증 경계**부터 설계한다.

## 위임 이후의 상태 일관성

### 장소 변경과 이전 숙박 결과의 무효화

장소를 바꾸면 이전 숙박 결과를 폐기하고 새 장소를 다시 조회한다.

### Router의 분류와 복합 요청 처리

한 번만 라우팅하는 구조는 복합 요청의 일부를 놓칠 수 있다.

### 숙소 조회와 예약 완료의 차이

조회 결과만으로 예약 완료를 주장할 수 없다.

[이전: 도구 기반 에이전트](../11-tool-agents/) / [시리즈 목차](../) / [다음: MCP 서버](../13-mcp-servers/)
