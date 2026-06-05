from __future__ import annotations

from mcp_server.qcad_adapter import import_dxf_to_qcad


def main() -> None:
    dxf_path = "/Users/chaemin/test_CADly/outputs/qcad_test/test_qcad_001.dxf"

    result = import_dxf_to_qcad(
        dxf_path=dxf_path,
        qcad_app_path="/Applications/QCAD.app",
    )

    print("\n=== QCAD Import Test Result ===")
    print(f"ok: {result.get('ok')}")
    print(f"message: {result.get('message')}")
    print(f"path: {result.get('path')}")
    print(f"command: {result.get('command')}")

    if result.get("stdout"):
        print("\n--- stdout ---")
        print(result["stdout"])

    if result.get("stderr"):
        print("\n--- stderr ---")
        print(result["stderr"])


if __name__ == "__main__":
    main()