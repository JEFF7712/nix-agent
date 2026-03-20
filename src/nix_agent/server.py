import subprocess
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools.tool import Tool

from nix_agent.inspect import read_target
from nix_agent.models import OperationResult, PatchSet
from nix_agent.patching import apply_patch_set as apply_patch_set_mutation
from nix_agent.policy import classify_change
from nix_agent.system_apply import run_dry_activate, run_switch
from nix_agent.validation import needs_nix_format


def _build_mcp_notes(goal: str) -> tuple[bool, str]:
    normalized = goal.strip().lower()
    if "install" in normalized or "package" in normalized:
        return True, (
            "Package lookup should be resolved via mcp-nixos before apply_change."
        )
    if "option" in normalized or "setting" in normalized or "module knob" in normalized:
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

    def plan_change_tool(goal: str) -> dict[str, bool | str]:
        return plan_change(goal)

    def apply_patch_set(patch_set: PatchSet) -> dict[str, object]:
        return apply_patch_set_mutation(patch_set)

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

    def dry_activate_system(flake_uri: str) -> dict[str, object]:
        output = run_dry_activate(flake_uri)
        return {
            "dry_activate_output": output.output,
            "validation_ok": output.ok,
        }

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

    def apply_change_tool(
        intent: str, changed_files: list[str], flake_uri: str
    ) -> dict[str, object]:
        result = apply_change_workflow(intent, changed_files, flake_uri)
        return {
            "intent": result.intent,
            "status": result.status,
            "changed_files": result.changed_files,
            "policy_decision": result.policy_decision,
            "approval_required": result.approval_required,
            "validation_result": result.validation_result,
            "apply_result": result.apply_result,
            "rollback_target": result.rollback_target,
        }

    def get_operation_result_tool(operation_id: str) -> dict[str, str]:
        return {
            "operation_id": operation_id,
            "status": "pending",
            "detail": "operation tracking is not available in v1",
        }

    server._tools = {  # type: ignore[attr-defined]
        "inspect_state": server.add_tool(
            Tool.from_function(
                inspect_state,
                name="inspect_state",
                description="Inspect a local target file",
            )
        ),
        "plan_change": server.add_tool(
            Tool.from_function(
                plan_change_tool,
                name="plan_change",
                description="Describe whether mcp-nixos should handle the goal first",
            )
        ),
        "apply_patch_set": server.add_tool(
            Tool.from_function(
                apply_patch_set,
                name="apply_patch_set",
                description="Apply a small set of file replacements",
            )
        ),
        "run_formatters": server.add_tool(
            Tool.from_function(
                run_formatters,
                name="run_formatters",
                description="Run configured formatters for touched files",
            )
        ),
        "dry_activate_system": server.add_tool(
            Tool.from_function(
                dry_activate_system,
                name="dry_activate_system",
                description="Run nixos-rebuild dry-activate for a flake",
            )
        ),
        "classify_change": server.add_tool(
            Tool.from_function(
                classify_change_tool,
                name="classify_change",
                description="Check changed files for approval policy conflicts",
            )
        ),
        "apply_change": server.add_tool(
            Tool.from_function(
                apply_change_tool,
                name="apply_change",
                description="Execute the apply change workflow locally",
            )
        ),
        "get_operation_result": server.add_tool(
            Tool.from_function(
                get_operation_result_tool,
                name="get_operation_result",
                description="Return a placeholder view of a tracked operation",
            )
        ),
    }
    return server


def apply_change_workflow(
    intent: str, changed_files: list[str], flake_uri: str
) -> OperationResult:
    decision = classify_change(changed_files, operation="switch")
    if decision.approval_required:
        return OperationResult(
            intent=intent,
            status="approval_required",
            changed_files=changed_files,
            policy_decision=decision.policy_decision,
            approval_required=True,
            validation_result=decision.reason,
        )

    validation = run_dry_activate(flake_uri)
    if not validation.ok:
        return OperationResult(
            intent=intent,
            status="validation_failed",
            changed_files=changed_files,
            policy_decision=decision.policy_decision,
            approval_required=False,
            validation_result=validation.output,
        )

    switch_result = run_switch(flake_uri)
    return OperationResult(
        intent=intent,
        status="applied",
        changed_files=changed_files,
        policy_decision=decision.policy_decision,
        approval_required=False,
        validation_result=validation.output,
        apply_result=switch_result,
    )
