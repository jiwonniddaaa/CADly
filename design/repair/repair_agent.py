from __future__ import annotations

from langgraph.graph import StateGraph, END

from design.state import CADlyGenerationState
from design.repair.verification_node import verify_generated_floorplan


def build_repair_agent():
    graph = StateGraph(CADlyGenerationState)

    graph.add_node("verify_generated_floorplan", verify_generated_floorplan)

    graph.set_entry_point("verify_generated_floorplan")
    graph.add_edge("verify_generated_floorplan", END)

    return graph.compile()


repair_agent = build_repair_agent()