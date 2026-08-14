from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.orchestration.agents import run_sub_agent
from app.orchestration.guardrails import check_prompt_injection

KNOWN_SOURCES = ("website", "catalog", "tech_doc", "digital_asset")


def _merge_agent_results(a: dict, b: dict) -> dict:
    """Reducer for the agent_results field — each sub-agent node contributes
    its own {source_type: result} entry; this merges them without any node
    overwriting another's output."""
    merged = dict(a or {})
    merged.update(b or {})
    return merged


class OrchestrationState(TypedDict):
    temp_request_id: str
    user_text: str
    sources_selected: list[str]
    urls: dict[str, str]
    guardrail_blocked: bool
    guardrail_reason: str | None
    agent_results: Annotated[dict, _merge_agent_results]


def guardrails_node(state: OrchestrationState) -> dict:
    result = check_prompt_injection(state["user_text"])
    return {"guardrail_blocked": result["blocked"], "guardrail_reason": result["reason"]}


def route_after_guardrails(state: OrchestrationState):
    if state["guardrail_blocked"]:
        # Blocked input never reaches the Supervisor's routing logic or any
        # sub-agent — short-circuit straight to END.
        return END

    selected = [s for s in state["sources_selected"] if s in KNOWN_SOURCES]
    return selected if selected else "merge"


def _make_agent_node(source_type: str):
    def node(state: OrchestrationState) -> dict:
        url = (state.get("urls") or {}).get(source_type)
        result = run_sub_agent(source_type, state["temp_request_id"], state["user_text"], url)
        return {"agent_results": {source_type: result}}

    return node


def merge_node(state: OrchestrationState) -> dict:
    return {}  # join point only — persistence happens in service.py after the graph finishes


def _build_graph():
    graph = StateGraph(OrchestrationState)
    graph.add_node("guardrails", guardrails_node)
    for source in KNOWN_SOURCES:
        graph.add_node(source, _make_agent_node(source))
    graph.add_node("merge", merge_node)

    graph.add_edge(START, "guardrails")
    graph.add_conditional_edges("guardrails", route_after_guardrails, [*KNOWN_SOURCES, "merge", END])
    for source in KNOWN_SOURCES:
        graph.add_edge(source, "merge")
    graph.add_edge("merge", END)

    return graph.compile()


graph_app = _build_graph()
