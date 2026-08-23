import shlex

from nix_agent.tools.switch import switch

_HINT = (
    "Run tty_command in a real terminal once. After that generation "
    "activates programs.nix-agent.privilegedAutomation (or equivalent "
    "NOPASSWD rules), sudo -n works and this command is no longer needed."
)


def _tty_command(command_form: object) -> str | None:
    if not isinstance(command_form, list) or not command_form:
        return None
    argv = [str(part) for part in command_form]
    if argv[:2] == ["sudo", "-n"]:
        argv = ["sudo", *argv[2:]]
    elif argv[0] != "sudo":
        argv = ["sudo", *argv]
    return shlex.join(argv)


def bootstrap_rebuild(
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """First privileged switch: sudo -n, or a one-shot TTY command.

    Same activation as switch(). A missing NOPASSWD rule becomes
    needs_bootstrap instead of hanging on a password prompt.
    """
    out = switch(flake_uri=flake_uri, mode=mode)
    privilege = out.get("privilege")
    if not isinstance(privilege, dict):
        return out
    command_form = privilege.get("command_form", out.get("command"))
    tty_command = _tty_command(command_form)
    result = {
        **out,
        "status": "needs_bootstrap",
        "hint": _HINT,
    }
    if tty_command is not None:
        result["tty_command"] = tty_command
    return result
