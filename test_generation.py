from __future__ import annotations

from design.mcp_generation.run_qcad_node import run_qcad_node


def main() -> None:
    state = {
        "generation_mode": "qcad",
        "name": "test_qcad_001",
        "qcad_output_dir": "outputs/qcad_test",
        "graph_data": {
            "rooms": [
                {
                    "id": "living_room1",
                    "type": 0,
                    "area": 30.0,
                },
                {
                    "id": "kitchen1",
                    "type": 1,
                    "area": 12.0,
                },
                {
                    "id": "bedroom1",
                    "type": 2,
                    "area": 15.0,
                },
                {
                    "id": "bathroom1",
                    "type": 3,
                    "area": 6.0,
                },
            ],
            "edges": [
                {
                    "source": "living_room1",
                    "target": "kitchen1",
                },
                {
                    "source": "living_room1",
                    "target": "bedroom1",
                },
                {
                    "source": "living_room1",
                    "target": "bathroom1",
                },
            ],
            "area_for_generation": 63.0,
        },
    }

    result = run_qcad_node(state)

    print("\n=== Run QCAD Node Test ===")
    print(f"status: {result.get('status')}")
    print(f"message: {result.get('message')}")
    print(f"dxf_path: {result.get('dxf_path')}")
    print(f"qcad_dxf_path: {result.get('qcad_dxf_path')}")
    print(f"qcad_generation_result: {result.get('qcad_generation_result')}")


if __name__ == "__main__":
    main()