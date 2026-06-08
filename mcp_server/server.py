from mcp.server.fastmcp import FastMCP
from mcp_server.autocad_adapter import import_dxf_to_autocad
from mcp_server.rhino_adapter import import_dxf_to_rhino
from mcp_server.qcad_adapter import import_dxf_to_qcad

mcp = FastMCP("CADly-cad-import-server")


@mcp.tool()
def import_to_autocad(dxf_path: str) -> dict:
    return import_dxf_to_autocad(dxf_path)


@mcp.tool()
def import_to_rhino(dxf_path: str, rhino_exe_path: str) -> dict:
    return import_dxf_to_rhino(dxf_path, rhino_exe_path)


@mcp.tool()
def import_to_qcad(dxf_path: str, qcad_app_path: str | None = None) -> dict:
    return import_dxf_to_qcad(dxf_path, qcad_app_path)


if __name__ == "__main__":
    mcp.run()