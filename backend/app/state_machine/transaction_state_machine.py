"""
Formal Finite State Machine (FSM) for Transaction Lifecycle.
Enforces legal transitions and prevents illegal status jumps.
"""

from enum import Enum
from typing import Set, Dict


class TransactionState(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    RECONCILING = "RECONCILING"
    RETRY_ALLOWED = "RETRY_ALLOWED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    ESCALATED = "ESCALATED"


class InvalidStateTransitionException(Exception):
    def __init__(self, from_state: str, to_state: str, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(f"Illegal transition: Cannot transition from {from_state} to {to_state}. {reason}".strip())


LEGAL_TRANSITIONS: Dict[TransactionState, Set[TransactionState]] = {
    TransactionState.AUTHORIZED: {TransactionState.PROPOSED, TransactionState.BLOCKED},
    TransactionState.PROPOSED: {TransactionState.APPROVED, TransactionState.BLOCKED},
    TransactionState.APPROVED: {TransactionState.SUBMITTED, TransactionState.BLOCKED},
    TransactionState.SUBMITTED: {
        TransactionState.COMPLETED,
        TransactionState.PENDING,
        TransactionState.FAILED,
        TransactionState.UNKNOWN,
    },
    TransactionState.PENDING: {
        TransactionState.COMPLETED,
        TransactionState.FAILED,
        TransactionState.CANCEL_REQUESTED,
        TransactionState.UNKNOWN,
    },
    TransactionState.UNKNOWN: {TransactionState.RECONCILING},
    TransactionState.RECONCILING: {
        TransactionState.COMPLETED,
        TransactionState.RETRY_ALLOWED,
        TransactionState.CANCEL_REQUESTED,
        TransactionState.ESCALATED,
        TransactionState.FAILED,
    },
    TransactionState.RETRY_ALLOWED: {TransactionState.SUBMITTED, TransactionState.ESCALATED},
    TransactionState.CANCEL_REQUESTED: {
        TransactionState.CANCELLED,
        TransactionState.ESCALATED,
    },
    # Terminal states have no outbound transitions
    TransactionState.COMPLETED: set(),
    TransactionState.BLOCKED: set(),
    TransactionState.FAILED: set(),
    TransactionState.CANCELLED: set(),
    TransactionState.ESCALATED: set(),
}

TERMINAL_STATES = {
    TransactionState.COMPLETED,
    TransactionState.BLOCKED,
    TransactionState.FAILED,
    TransactionState.CANCELLED,
    TransactionState.ESCALATED,
}


class TransactionStateMachine:
    @staticmethod
    def is_legal(from_state: str, to_state: str) -> bool:
        try:
            curr = TransactionState(from_state)
            target = TransactionState(to_state)
            return target in LEGAL_TRANSITIONS.get(curr, set())
        except ValueError:
            return False

    @staticmethod
    def transition(from_state: str, to_state: str, reason: str = "") -> str:
        try:
            curr = TransactionState(from_state)
            target = TransactionState(to_state)
        except ValueError as e:
            raise InvalidStateTransitionException(from_state, to_state, f"Invalid state value: {e}")

        allowed = LEGAL_TRANSITIONS.get(curr, set())
        if target not in allowed:
            raise InvalidStateTransitionException(
                curr.value,
                target.value,
                f"Valid outbound states from {curr.value} are: {[s.value for s in allowed]}"
            )
        return target.value

    @staticmethod
    def is_terminal(state: str) -> bool:
        try:
            return TransactionState(state) in TERMINAL_STATES
        except ValueError:
            return False
