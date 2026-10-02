from typing import Set, Dict
from src.schemas.types import IntentState

class InvalidStateTransitionError(Exception):
    def __init__(self, from_state: IntentState, to_state: IntentState, reason: str = ""):
        super().__init__(f"Invalid state transition from {from_state} to {to_state}. {reason}")
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason

class TransactionStateMachine:
    """
    Enforces deterministic state transitions for an IntentGuard transaction lifecycle:
    AUTHORIZED -> PROPOSED -> VALIDATED -> EXECUTING -> [COMPLETED | UNKNOWN]
    UNKNOWN -> RECONCILING -> [COMPLETED | EXECUTING (controlled retry) | ESCALATED | CANCEL_REQUESTED]
    CANCEL_REQUESTED -> CANCELLED | ESCALATED
    """

    ALLOWED_TRANSITIONS: Dict[IntentState, Set[IntentState]] = {
        IntentState.AUTHORIZED: {IntentState.PROPOSED, IntentState.BLOCKED},
        IntentState.PROPOSED: {IntentState.VALIDATED, IntentState.EXECUTING, IntentState.BLOCKED, IntentState.COMPLETED},
        IntentState.VALIDATED: {IntentState.EXECUTING, IntentState.BLOCKED, IntentState.COMPLETED},
        IntentState.EXECUTING: {IntentState.COMPLETED, IntentState.UNKNOWN, IntentState.CANCEL_REQUESTED, IntentState.ESCALATED, IntentState.BLOCKED},
        IntentState.UNKNOWN: {IntentState.RECONCILING, IntentState.ESCALATED},
        IntentState.RECONCILING: {IntentState.COMPLETED, IntentState.EXECUTING, IntentState.CANCEL_REQUESTED, IntentState.ESCALATED, IntentState.UNKNOWN},
        IntentState.CANCEL_REQUESTED: {IntentState.CANCELLED, IntentState.ESCALATED},
        IntentState.CANCELLED: set(), # Terminal
        IntentState.COMPLETED: set(), # Terminal
        IntentState.BLOCKED: {IntentState.PROPOSED}, # A new proposal may be submitted if intent remains unfulfilled
        IntentState.ESCALATED: {IntentState.COMPLETED, IntentState.CANCELLED} # Human review resolution
    }

    @classmethod
    def can_transition(cls, current_state: IntentState, next_state: IntentState) -> bool:
        if current_state == next_state:
            return True
        allowed = cls.ALLOWED_TRANSITIONS.get(current_state, set())
        return next_state in allowed

    @classmethod
    def transition(cls, current_state: IntentState, next_state: IntentState, context_msg: str = "") -> IntentState:
        if not cls.can_transition(current_state, next_state):
            raise InvalidStateTransitionError(current_state, next_state, context_msg)
        return next_state
