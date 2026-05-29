from pathlib import Path
from app.core.config import settings

def to_image_url(image_path: str | None) -> str | None:
    if not image_path:
        return None

    raw_root = Path(settings.raw_storage_path).resolve()
    path = Path(image_path).resolve()

    try:
        rel = path.relative_to(raw_root)
    except ValueError:
        return None

    return f'/static/raw/{rel.as_posix()}'
