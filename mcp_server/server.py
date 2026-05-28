from mcp.server.fastmcp import FastMCP
from mcp_server.autocad_adapter import import_dxf_to_autocad
from mcp_server.rhino_adapter import import_dxf_to_rhino

mcp = FastMCP("CADly-cad-import-server")


@mcp.tool()
def import_to_autocad(dxf_path: str) -> dict:
    """
    Import a HouseDiffusion DXF result into AutoCAD.
    """
    return import_dxf_to_autocad(dxf_path)


@mcp.tool()
def import_to_rhino(dxf_path: str, rhino_exe_path: str) -> dict:
    """
    Open a HouseDiffusion DXF result in Rhino.
    """
    return import_dxf_to_rhino(dxf_path, rhino_exe_path)


if __name__ == "__main__":
    mcp.run()