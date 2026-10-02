import pytest
from src.schemas.types import IntentState
from src.gateway.state_machine import TransactionStateMachine, InvalidStateTransitionError

def test_legal_state_transitions():
    assert TransactionStateMachine.can_transition(IntentState.AUTHORIZED, IntentState.PROPOSED)
    assert TransactionStateMachine.can_transition(IntentState.PROPOSED, IntentState.VALIDATED)
    assert TransactionStateMachine.can_transition(IntentState.VALIDATED, IntentState.EXECUTING)
    assert TransactionStateMachine.can_transition(IntentState.EXECUTING, IntentState.COMPLETED)
    assert TransactionStateMachine.can_transition(IntentState.EXECUTING, IntentState.UNKNOWN)
    assert TransactionStateMachine.can_transition(IntentState.UNKNOWN, IntentState.RECONCILING)
    assert TransactionStateMachine.can_transition(IntentState.RECONCILING, IntentState.COMPLETED)
    assert TransactionStateMachine.can_transition(IntentState.RECONCILING, IntentState.EXECUTING) # Controlled retry

def test_illegal_state_transitions():
    with pytest.raises(InvalidStateTransitionError):
        # Cannot jump from AUTHORIZED directly to COMPLETED without execution
        TransactionStateMachine.transition(IntentState.AUTHORIZED, IntentState.COMPLETED)

    with pytest.raises(InvalidStateTransitionError):
        # Cannot transition out of terminal COMPLETED state
        TransactionStateMachine.transition(IntentState.COMPLETED, IntentState.EXECUTING)

    with pytest.raises(InvalidStateTransitionError):
        # Cannot jump from UNKNOWN directly to COMPLETED without reconciliation
        TransactionStateMachine.transition(IntentState.UNKNOWN, IntentState.COMPLETED)
