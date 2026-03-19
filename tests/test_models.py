from nix_agent.models import OperationResult


def test_operation_result_defaults():
    result = OperationResult(intent="inspect firewall")
    assert result.intent == "inspect firewall"
    assert result.changed_files == []
    assert result.approval_required is False
