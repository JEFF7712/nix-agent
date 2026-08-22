import re

# sudo refused because there is no interactive terminal or askpass helper.
# `sudo -n` fails immediately with "a password is required" instead of hanging
# on a prompt the MCP server cannot answer.
_SUDO_NO_AUTH = re.compile(
    r"sudo: (a terminal is required|a password is required|"
    r"no askpass program|no tty present)",
    re.IGNORECASE,
)


def sudo_argv(cmd: list[str]) -> list[str]:
    """Privileged argv: non-interactive sudo, then the resolved command."""
    return ["sudo", "-n", *cmd]


def sudo_diagnosis(argv: list[str], output: str) -> dict[str, object] | None:
    if not _SUDO_NO_AUTH.search(output):
        return None
    return {
        "cause": "sudo could not authenticate non-interactively",
        "detail": (
            "This operation needs root via sudo, but there is no TTY/askpass and "
            "no passwordless rule matched this command form. nix-agent invokes "
            "sudo -n with the resolved store path of the binary so a missing "
            "NOPASSWD rule fails immediately; a NOPASSWD rule must match that "
            "exact argv (without the sudo -n prefix)."
        ),
        "command_form": argv,
        "fixes": [
            "Enable programs.nix-agent.privilegedAutomation for this user "
            "and flake (documented default), or add a NOPASSWD sudoers "
            "rule for this command's store path.",
            "Lower trust: set SUDO_ASKPASS and run with sudo -A, or run "
            "from an interactive session.",
        ],
    }
