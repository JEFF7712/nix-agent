from pathlib import Path


def replace_file_contents(path: str | Path, content: str) -> list[str]:
    target = Path(path)
    target.write_text(content)
    return [str(target)]
