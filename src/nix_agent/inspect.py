from pathlib import Path


def read_target(path: str | Path) -> dict[str, str]:
    target = Path(path)
    return {"path": str(target), "content": target.read_text()}
