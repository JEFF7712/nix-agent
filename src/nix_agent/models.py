from dataclasses import dataclass, field


@dataclass
class Patch:
    path: str
    content: str


@dataclass
class PatchSet:
    patches: list[Patch] = field(default_factory=list)


__all__ = ["Patch", "PatchSet"]
