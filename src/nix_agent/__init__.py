__all__ = ["build_server"]


def __getattr__(name: str):
    if name == "build_server":
        from .server import build_server

        return build_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
