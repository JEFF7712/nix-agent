import re

# sudo refused because there is no interactive terminal or askpass helper.
_SUDO_NO_AUTH = re.compile(
    r"sudo: (a terminal is required|a password is required|"
    r"no askpass program|no tty present)",
    re.IGNORECASE,
)


def sudo_diagnosis(argv: list[str], output: str) -> dict[str, object] | None:
    if not _SUDO_NO_AUTH.search(output):
        return None
    return {
        "cause": "sudo could not authenticate non-interactively",
        "detail": (
            "This operation needs root via sudo, but there is no TTY/askpass and "
            "no passwordless rule matched this command form. nix-agent invokes "
            "sudo with the resolved store path of the binary; a NOPASSWD "
            "rule must match that exact argv."
        ),
        "command_form": argv,
        "fixes": [
            "Add a NOPASSWD sudoers rule for this command's store path, or",
            "Set SUDO_ASKPASS and run with sudo -A, or",
            "Run from an interactive session.",
        ],
    }
