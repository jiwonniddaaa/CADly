# main.py
from __future__ import annotations

import argparse
import asyncio
from langchain_core.messages import HumanMessage, AIMessage

import planner.orchestrator as planning_module


class DryRunDesignApp:
    """GPU 생성 직전까지만 테스트하기 위한 가짜 design orchestrator."""

    def invoke(self, state: dict) -> dict:
        return {
            "status": "dry_run_success",
            "message": "CPU dry-run: 설계 오케스트레이터 호출 직전까지 정상 도달했습니다.",
            "graph_json_path": state.get("graph_json_path"),
            "model_path": state.get("model_path"),
            "out_dir": state.get("out_dir"),
            "name": state.get("name"),
            "svg_path": None,
            "dxf_path": None,
        }


def enable_dry_run():
    planning_module.build_design_orchestrator = lambda: DryRunDesignApp()


def print_ai_response(state: dict):
    messages = state.get("messages", [])

    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            print(f"\nCADly: {msg.content}\n")

            if state.get("route") == "reference_agent":
                references = state.get("references", [])

                if references:
                    print("📷 Reference Images:")

                    for i, ref in enumerate(references, start=1):
                        print(f"\n[{i}] {ref.get('title', 'Untitled')}")
                        print(f"imageUrl: {ref.get('imageUrl')}")
                        print(f"thumbnail: {ref.get('thumbnail')}")
                        print(f"sourceUrl: {ref.get('sourceUrl')}")

                    print()

            return

    print("\nCADly: 응답을 생성하지 못했습니다.\n")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="GPU 생성 없이 설계 오케스트레이터 호출 직전까지만 테스트",
    )
    args = parser.parse_args()

    if args.dry_run:
        enable_dry_run()
        print("CPU dry-run 모드입니다. 실제 도면 생성은 실행하지 않습니다.\n")

    app = planning_module.planning_orchestrator

    state = {
        "messages": [],
        "spaces": [],
        "edges": [],
        "references": [],
        "site_analysis": None,
        "concept": None,
        "awaiting_concept_confirmation": False,
    }

    print("CADly 챗봇을 시작합니다.")
    print("종료하려면 exit 또는 quit 입력\n")

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in {"exit", "quit"}:
            print("CADly 종료")
            break

        if not user_input:
            continue

        state["messages"].append(HumanMessage(content=user_input))

        try:
            result = await app.ainvoke(state)

            # LangGraph 결과를 다음 턴 state로 유지
            state.update(result)

            print_ai_response(state)

        except Exception as e:
            print("\n오류가 발생했습니다.")
            print(f"{type(e).__name__}: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())