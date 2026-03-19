import subprocess
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools.tool import Tool

from nix_agent.inspect import read_target
from nix_agent.models import OperationResult, PatchSet
from nix_agent.patching import replace_file_contents
from nix_agent.policy import classify_change
from nix_agent.system_apply import run_dry_activate, run_switch
from nix_agent.validation import needs_nix_format


def _build_mcp_notes(goal: str) -> tuple[bool, str]:
    normalized = goal.strip().lower()
    if "install" in normalized or "package" in normalized:
        return True, (
            "Package lookup should be resolved via mcp-nixos before apply_change."
        )
    if "option" in normalized:
        return True, (
            "Option discovery should be resolved via mcp-nixos before apply_change."
        )
    return False, "No mcp-nixos boundary detected for this plan."


def plan_change(goal: str) -> dict[str, bool | str]:
    requires, notes = _build_mcp_notes(goal)
    return {
        "goal": goal,
        "requires_mcp_nixos": requires,
        "notes": notes,
    }


def build_server() -> FastMCP:
    server = FastMCP("nix-agent")

    @server.tool(name="inspect_state", description="Inspect a local target file")
    def inspect_state(
        path: str | Path | None = None,
        target: dict[str, str] | None = None,
    ) -> dict[str, str]:
        candidate: str | Path | None
        if target is not None:
            candidate = target.get("path")
            if candidate is None:
                raise ValueError("target must include a path")
        elif path is not None:
            candidate = path
        else:
            raise ValueError("path or target is required")

        return read_target(candidate)

    @server.tool(
        name="plan_change",
        description="Describe whether mcp-nixos should handle the goal first",
    )
    def plan_change_tool(goal: str) -> dict[str, bool | str]:
        return plan_change(goal)

    @server.tool(
        name="apply_patch_set",
        description="Apply a small set of file replacements",
    )
    def apply_patch_set(patch_set: PatchSet) -> dict[str, list[str]]:
        changed_files: list[str] = []
        for patch in patch_set.patches:
            changed_files.extend(replace_file_contents(patch.path, patch.content))
        return {"changed_files": changed_files}

    @server.tool(
        name="run_formatters",
        description="Run configured formatters for touched files",
    )
    def run_formatters(changed_files: list[str]) -> dict[str, str]:
        formatter_messages: list[str] = []
        for path in changed_files:
            if not needs_nix_format(path):
                continue
            result = subprocess.run(
                ["nixpkgs-fmt", path], capture_output=True, text=True
            )
            message = (result.stdout or result.stderr).strip()
            formatter_messages.append(f"{path}: {message or 'formatted'}")

        output = "\n".join(formatter_messages) if formatter_messages else "no nix files"
        return {"formatter_output": output}

    @server.tool(
        name="dry_activate_system",
        description="Run nixos-rebuild dry-activate for a flake",
    )
    def dry_activate_system(flake_uri: str) -> dict[str, str]:
        output = run_dry_activate(flake_uri)
        return {"dry_activate_output": output}

    @server.tool(
        name="classify_change",
        description="Check changed files for approval policy conflicts",
    )
    def classify_change_tool(
        changed_files: list[str],
        operation: str | None = None,
    ) -> dict[str, object]:
        decision = classify_change(changed_files, operation=operation)
        return {
            "policy_decision": decision.policy_decision,
            "approval_required": decision.approval_required,
            "reason": decision.reason,
            "risk_level": decision.risk_level,
            "matched_rules": decision.matched_rules,
        }

    @server.tool(
        name="apply_change",
        description="Execute the apply change workflow locally",
    )
    def apply_change_tool(
        intent: str, changed_files: list[str], flake_uri: str
    ) -> dict[str, object]:
        result = apply_change_workflow(intent, changed_files, flake_uri)
        return {
            "intent": result.intent,
            "changed_files": result.changed_files,
            "policy_decision": result.policy_decision,
            "approval_required": result.approval_required,
            "validation_result": result.validation_result,
            "apply_result": result.apply_result,
            "rollback_target": result.rollback_target,
        }

    @server.tool(
        name="get_operation_result",
        description="Return a placeholder view of a tracked operation",
    )
    def get_operation_result_tool(operation_id: str) -> dict[str, str]:
        return {
            "operation_id": operation_id,
            "status": "pending",
            "detail": "operation tracking is not available in v1",
        }

    server._tools = {
        component.name: component
        for component in server._local_provider._components.values()
        if isinstance(component, Tool)
    }
    return server


def apply_change_workflow(
    intent: str, changed_files: list[str], flake_uri: str
) -> OperationResult:
    decision = classify_change(changed_files, operation="switch")
    if decision.approval_required:
        return OperationResult(
            intent=intent,
            changed_files=changed_files,
            policy_decision=decision.policy_decision,
            approval_required=True,
            validation_result=decision.reason,
        )

    validation = run_dry_activate(flake_uri)
    switch_result = run_switch(flake_uri)
    return OperationResult(
        intent=intent,
        changed_files=changed_files,
        policy_decision=decision.policy_decision,
        approval_required=False,
        validation_result=validation,
        apply_result=switch_result,
    )
