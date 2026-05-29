from __future__ import annotations

from langchain_core.messages import HumanMessage, AIMessage

from planning.orchestrator import build_planning_orchestrator
from design.orchestrator import build_design_orchestrator

def get_last_ai_message(messages: list):
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg
    return None

def print_images(state: dict):
    references = state.get("references", [])

    if not references:
        return
    
    for i, ref in enumerate(references, start=1):
        print(f"\n[{i}] {ref.get('title', 'Untitled')}")
        print(f"imageUrl: {ref.get('imageUrl')}")
        print(f"thumbnail: {ref.get('thumbnail')}")
        print(f"sourceUrl: {ref.get('sourceUrl')}")

    print()

def print_design_output(state: dict):
    svg_path = state.get("svg_path")
    dxf_path = state.get("dxf_path")
    room_label_path = state.get("room_label_path")

    if not any([svg_path, dxf_path, room_label_path]):
        return

    if svg_path:
        print(f"SVG 도면이 생성되었습니다: {svg_path}")
    else:
        print("SVG 도면이 생성되지 않았습니다.")

    if dxf_path:
        print(f"DXF 도면이 생성되었습니다: {dxf_path}")
    else:
        print("DXF 도면이 생성되지 않았습니다.")
    
    print()

def print_response(state: dict):
    messages = state.get("messages", [])
    last_ai_message = get_last_ai_message(messages)

    if last_ai_message:
        print(f"\nCADly: {last_ai_message.content}\n")
    else:
        print("\nCADly: 응답을 생성하지 못했습니다.\n")
    
    print_images(state)
    print_design_output(state)

def update_state_without_messages(state: dict, results: dict):
    update = {
        key: value
        for key, value in results.items()
        if key != "messages"
    }

    state.update(update)

def main():
    planning_app = build_planning_orchestrator()
    design_app = build_design_orchestrator()

    conversation_state = {
        "messages": [],
        "active_orchestrator": "planning",
        "planning_state": {},
        "design_state": {},
    }

    print("CADly 챗봇을 시작합니다.")
    print("종료하려면 exit 또는 quit 입력\n")

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in {"exit", "quit"}:
            print("CADly를 종료합니다.")
            break

        if not user_input:
            continue

        conversation_state["messages"].append(
                HumanMessage(content=user_input)
        )
        
        active_orchestrator = conversation_state.get("active_orchestrator")

        if active_orchestrator == "design":
            result = design_app.invoke(
                {
                    **conversation_state.get("design_state", {}),
                    "messages": conversation_state["messages"],
                    "user_input": user_input,
                }
            )

            update_state_without_messages(conversation_state["design_state"], result)

        else:
            result = planning_app.invoke(
                {
                    **conversation_state.get("planning_state", {}),
                    "messages": conversation_state["messages"],
                    "user_input": user_input,
                }
            )

            update_state_without_messages(conversation_state["planning_state"], result)

            if result.get("active_orchestrator") == "design":
                conversation_state["active_orchestrator"] = "design"
                conversation_state["design_state"] = result.get("design_state", {})

        result_messages = result.get("messages", [])
        if result_messages:
            conversation_state["messages"].extend(result_messages)

        print_response(result)

if __name__ == "__main__":
    main()