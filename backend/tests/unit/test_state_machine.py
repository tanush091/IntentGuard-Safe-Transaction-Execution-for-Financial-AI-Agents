"""
Unit tests for the Formal Transaction State Machine.
"""

import pytest
from backend.app.state_machine.transaction_state_machine import (
    TransactionStateMachine,
    TransactionState,
    InvalidStateTransitionException
)


def test_legal_transitions():
    assert TransactionStateMachine.transition("AUTHORIZED", "PROPOSED") == "PROPOSED"
    assert TransactionStateMachine.transition("PROPOSED", "APPROVED") == "APPROVED"
    assert TransactionStateMachine.transition("APPROVED", "SUBMITTED") == "SUBMITTED"
    assert TransactionStateMachine.transition("SUBMITTED", "COMPLETED") == "COMPLETED"
    assert TransactionStateMachine.transition("SUBMITTED", "UNKNOWN") == "UNKNOWN"
    assert TransactionStateMachine.transition("UNKNOWN", "RECONCILING") == "RECONCILING"
    assert TransactionStateMachine.transition("RECONCILING", "COMPLETED") == "COMPLETED"
    assert TransactionStateMachine.transition("RECONCILING", "RETRY_ALLOWED") == "RETRY_ALLOWED"


def test_illegal_transitions_raise_exception():
    # Direct jump from AUTHORIZED to COMPLETED without approval/submission
    with pytest.raises(InvalidStateTransitionException):
        TransactionStateMachine.transition("AUTHORIZED", "COMPLETED")

    # Outbound from terminal state COMPLETED
    with pytest.raises(InvalidStateTransitionException):
        TransactionStateMachine.transition("COMPLETED", "SUBMITTED")

    # Outbound from terminal state BLOCKED
    with pytest.raises(InvalidStateTransitionException):
        TransactionStateMachine.transition("BLOCKED", "APPROVED")


def test_terminal_states():
    assert TransactionStateMachine.is_terminal("COMPLETED") is True
    assert TransactionStateMachine.is_terminal("BLOCKED") is True
    assert TransactionStateMachine.is_terminal("ESCALATED") is True
    assert TransactionStateMachine.is_terminal("AUTHORIZED") is False
    assert TransactionStateMachine.is_terminal("SUBMITTED") is False
