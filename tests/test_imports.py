from nix_agent.server import build_server


def test_build_server_exists():
    assert callable(build_server)
