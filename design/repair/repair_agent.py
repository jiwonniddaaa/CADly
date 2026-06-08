from __future__ import annotations

from langgraph.graph import StateGraph, END

from design.state import CADlyGenerationState
from design.repair.verification_node import verify_generated_floorplan
from design.repair.classify_node import classify_node
from design.repair.postprocess_node import postprocess_node
from design.repair.resample_node import resample_node
from design.repair.final_node import final_node

def route_after_classify(state: CADlyGenerationState) -> str:
    route = state.get("repair_route")

    if route == "final_node":
        return "final_node"

    if route == "postprocess_node":
        return "postprocess_node"

    if route == "resample_node":
        return "resample_node"

    return "final_node"

def route_after_retry_step(state: CADlyGenerationState) -> str:
    if state.get("repair_route") == "verification_node":
        return "verification_node"

    return "final_node"

def build_repair_agent():
    graph = StateGraph(CADlyGenerationState)

    graph.add_node("verification_node", verify_generated_floorplan)
    graph.add_node("classify_node", classify_node)
    graph.add_node("postprocess_node", postprocess_node)
    graph.add_node("resample_node", resample_node)
    graph.add_node("final_node", final_node)

    graph.set_entry_point("verification_node")
    graph.add_edge("verification_node", "classify_node")

    graph.add_conditional_edges(
        "classify_node",
        route_after_classify,
        {
            "final_node": "final_node",
            "postprocess_node": "postprocess_node",
            "resample_node": "resample_node",
        }
    )
    
    graph.add_conditional_edges(
        "postprocess_node",
        route_after_retry_step,
        {
            "verification_node": "verification_node",
            "final_node": "final_node",
        }
    )

    graph.add_conditional_edges(
        "resample_node",
        route_after_retry_step,
        {
            "verification_node": "verification_node",
            "final_node": "final_node",
        }
    )

    graph.add_edge("final_node", END)

    return graph.compile()


repair_agent = build_repair_agent()