from __future__ import annotations
import os
import json
import subprocess
import sys
from pathlib import Path
from typing import List

from langgraph.graph import StateGraph, END

from design.state import CADlyGenerationState
from design.path_utils import resolve_hd_path, HD_ROOT
from design.validation_node import validate_generator_graph
from design.sampling_node import run_sampling
from design.repair.repair_agent import repair_agent
from design.cad_import_node import cad_import_node

PROJECT_ROOT = Path(__file__).resolve().parents[1]   # CADly/
HD_ROOT = PROJECT_ROOT / "house_diffusion"            # CADly/house_diffusion

def save_graph_json(state: CADlyGenerationState) -> CADlyGenerationState:
    graph_data = state.get("graph_data")

    if not graph_data:
        return {
            **state,
            "status": "save_failed",
            "message": "No graph data to save.",
        }

    out_dir = resolve_hd_path(state.get("out_dir", "outputs/CADly"))
    name = state.get("name", "floorplan")

    input_dir = out_dir / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)

    graph_json_path = input_dir / f"{name}_graph.json"

    try:
        with open(graph_json_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2, ensure_ascii=False)
    
    except Exception as e:
        return {
            **state,
            "status": "save_failed",
            "message": f"Failed to save graph JSON: {e}",
        }

    return {
        **state,
        "status": "graph_saved",
        "graph_json_path": str(graph_json_path),
        "message": f"Graph JSON saved to {graph_json_path}",
    }

def run_repair_agent(state: CADlyGenerationState) -> CADlyGenerationState:
    return repair_agent.invoke(state)

def should_continue_after_validation(state: CADlyGenerationState) -> str:
    if state.get("status") in ["validation_failed", "error"]:
        return "end"
    return "continue"

def should_continue_after_save_graph(state: CADlyGenerationState) -> str:
    if state.get("status") in ["save_failed", "error"]:
        return "end"
    return "continue"

def should_continue_after_sampling(state: CADlyGenerationState) -> str:
    if state.get("status") in ["sampling_failed", "error"]:
        return "end"
    return "continue"

def should_continue_after_repair(state: CADlyGenerationState) -> str:
    if state.get("status") in [
        "repair_failed",
        "verification_failed",
        "error",
    ]:
        return "end"

    return "continue"

def build_design_orchestrator():
    graph = StateGraph(CADlyGenerationState)
    
    graph.add_node("validate_generator_graph", validate_generator_graph)
    graph.add_node("save_graph_json", save_graph_json)
    graph.add_node("run_sampling", run_sampling)
    graph.add_node("run_repair_agent", run_repair_agent)
    graph.add_node("cad_import_node", cad_import_node)

    graph.set_entry_point("validate_generator_graph")

    graph.add_conditional_edges(
        "validate_generator_graph",
        should_continue_after_validation,
        {
            "continue": "save_graph_json",
            "end": END,
        },
    )

    graph.add_conditional_edges(
        "save_graph_json",
        should_continue_after_save_graph,
        {
            "continue": "run_sampling",
            "end": END,
        },
    )

    graph.add_conditional_edges(
        "run_sampling",
        should_continue_after_sampling,
        {
            "continue": "run_repair_agent",
            "end": END,
        },
    )

    graph.add_conditional_edges(
        "run_repair_agent",
        should_continue_after_repair,
        {
            "continue": "cad_import_node",
            "end": END,
        },
    )

    graph.add_edge("cad_import_node", END)

    return graph.compile()