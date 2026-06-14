from __future__ import annotations

import json
from pathlib import Path

from design.repair.repair_agent import repair_agent


def main():
    input_dxf = Path("claude_qcad_test/samples/sample_house.dxf").resolve()
    input_svg = Path("claude_qcad_test/samples/sample_house.svg").resolve()
    room_label_json = Path("claude_qcad_test/samples/sample_rooms.json").resolve()

    output_dir = Path("outputs/repair_agent_test").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "messages": [],
        "name": "sample_house",
        "status": "completed",

        "svg_path": str(input_svg),
        "dxf_path": str(input_dxf),
        "room_label_path": str(room_label_json),

        "out_dir": str(output_dir),

        "validation_errors": [],
        "verification_warnings": [],
        "repair_history": [],

        "resample_count": 0,
        "max_resamples": 0,
        "postprocess_count": 0,
        "max_postprocesses": 0,
    }
    result = repair_agent.invoke(state)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    print("\n=== Result paths ===")
    print("status:", result.get("status"))
    print("message:", result.get("message"))
    print("dxf_path:", result.get("dxf_path"))
    print("svg_path:", result.get("svg_path"))
    print("refined_dxf_path:", result.get("refined_dxf_path"))
    print("refined_svg_path:", result.get("refined_svg_path"))


if __name__ == "__main__":
    main()