from nix_agent.models import OperationResult, Patch


def test_operation_result_defaults():
    result = OperationResult(intent="inspect firewall")
    assert result.intent == "inspect firewall"
    assert result.changed_files == []
    assert result.approval_required is False


def test_patch_defaults_to_patch_operation_without_trust_fields():
    patch = Patch(path="/tmp/example", content="x")

    assert patch.operation == "patch"
