# Claude + QCAD MCP Multi-turn Refinement Test

이 폴더는 HouseDiffusion 결과물인 `DXF + SVG + room_label.json`을 받은 뒤,
**Claude 또는 scripted agent가 MCP 서버를 통해 QCAD를 실행하고 DXF를 수정하는 흐름**을 테스트하기 위한 최소 예제입니다.

핵심 흐름:

```text
client/run_multi_turn_qcad_agent.py
  → MCP stdio client
  → qcad_mcp/server.py
  → apply_refinement_plan tool
  → QCAD -autostart scripts/qcad_apply_refinement_plan_template.js
  → outputs/refined_final.dxf
```

## 폴더 구조

```text
claude_qcad_mcp_multi_turn_test/
  README.md
  requirements.txt
  .env.example

  samples/
    sample_house.dxf
    sample_house.svg
    sample_rooms.json

  qcad_mcp/
    server.py
    dxf_text_tools.py

  scripts/
    qcad_apply_refinement_plan_template.js

  client/
    run_multi_turn_qcad_agent.py

  outputs/
```

## 1. 설치

```bash
cd claude_qcad_mcp_multi_turn_test
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell이면:

```powershell
cd claude_qcad_mcp_multi_turn_test
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## 2. QCAD 경로 설정

`.env` 파일에서 `QCAD_BIN`을 본인 QCAD 실행 파일 경로로 바꾸세요.

macOS 예시:

```env
QCAD_BIN=/Applications/QCAD-Pro.app/Contents/MacOS/QCAD-Pro
```

또는 Community 버전이면:

```env
QCAD_BIN=/Applications/QCAD.app/Contents/MacOS/QCAD
```

Linux 예시:

```env
QCAD_BIN=/opt/qcad/qcad
```

Windows 예시:

```env
QCAD_BIN=C:\Program Files\QCAD\qcad.exe
```

## 3. QCAD MCP 수정 흐름 테스트

Claude 없이도 먼저 MCP 서버와 QCAD 실행이 되는지 확인할 수 있습니다.

```bash
python client/run_multi_turn_qcad_agent.py --mode scripted --backend qcad
```

성공하면 아래 파일이 생깁니다.

```text
outputs/step_01_layer_and_align.dxf
outputs/step_02_add_labels.dxf
outputs/step_02_preview.svg
outputs/refined_final.dxf
outputs/mcp_transcript.json
```

이 실행은 내부적으로 여러 번 MCP tool을 호출합니다.

```text
inspect_dxf
validate_geometry
apply_refinement_plan
validate_geometry
apply_refinement_plan
render_preview
validate_geometry
```

즉 단일 plan 적용이 아니라, 여러 턴으로 MCP와 주고받는 구조입니다.

## 4. Claude가 직접 여러 턴으로 MCP tool을 선택하게 실행

`.env`에 Anthropic API key를 넣으세요.

```env
ANTHROPIC_API_KEY=your_key
ANTHROPIC_MODEL=claude-sonnet-4-5
```

그다음 실행:

```bash
python client/run_multi_turn_qcad_agent.py --mode claude --backend qcad
```

이 모드에서는 Claude가 직접 다음 도구들을 선택해서 호출합니다.

```text
inspect_dxf
validate_geometry
apply_refinement_plan
render_preview
```

결과 로그는 다음 파일로 저장됩니다.

```text
outputs/claude_mcp_transcript.json
```

## 5. QCAD 없이 MCP 흐름만 확인하고 싶을 때

QCAD 설치 전에는 Python fallback으로 MCP tool 호출 흐름을 먼저 테스트할 수 있습니다.

```bash
python client/run_multi_turn_qcad_agent.py --mode scripted --backend python
```

주의: 이건 QCAD 실행 테스트가 아니라 MCP client/server와 DXF 수정 로직 테스트입니다.
QCAD 연결 확인은 반드시 `--backend qcad`로 해야 합니다.

## 6. 내 HouseDiffusion 결과로 테스트

예를 들어 기존 결과가 아래에 있다면:

```text
/path/to/generated.dxf
/path/to/generated_rooms.json
```

이렇게 실행합니다.

```bash
python client/run_multi_turn_qcad_agent.py \
  --mode scripted \
  --backend qcad \
  --input-dxf /path/to/generated.dxf \
  --room-label-json /path/to/generated_rooms.json \
  --output-dir outputs/my_house_test
```

Claude까지 붙이려면:

```bash
python client/run_multi_turn_qcad_agent.py \
  --mode claude \
  --backend qcad \
  --input-dxf /path/to/generated.dxf \
  --room-label-json /path/to/generated_rooms.json \
  --output-dir outputs/my_house_test
```

## 7. 현재 테스트 구현 범위

현재 QCAD script가 지원하는 refinement action은 3개입니다.

```text
normalize_layers
align_walls
add_room_labels
```

다음 단계에서 추가하기 좋은 action:

```text
snap_wall_endpoints
merge_collinear_walls
remove_duplicate_entities
move_room_labels_to_centers
add_door_openings
export_pdf
```

## 8. CADly에 붙일 때 위치

CADly에서는 HouseDiffusion export 뒤에 이 노드를 붙이면 됩니다.

```text
HouseDiffusion Generator
  → export_floorplan.py
  → qcad_refinement_node
  → final_verification_node
```

`client/run_multi_turn_qcad_agent.py`의 로직을 나중에 `design/qcad_refinement_node.py`로 옮기면 됩니다.
