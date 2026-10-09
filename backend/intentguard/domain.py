"""
Domain vocabulary and the intent state machine.

An *intent* is the business request an operator authorized. It is distinct from
an agent *proposal* (what the agent asked for), an *attempt* (one provider API
call made by the gateway), and an *effect* (a transaction actually observed at
the provider). Intent state is derived from attempts and effects, and every
change is checked against TRANSITIONS.
"""

from __future__ import annotations

from enum import StrEnum


class Operation(StrEnum):
    REFUND = "REFUND"
    PAYMENT_AUTHORIZATION = "PAYMENT_AUTHORIZATION"


class IntentState(StrEnum):
    AUTHORIZED = "AUTHORIZED"  # approved, nothing executed yet
    IN_FLIGHT = "IN_FLIGHT"  # an attempt is being submitted
    PENDING_SETTLEMENT = "PENDING_SETTLEMENT"  # intended effect exists, provider still pending
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"  # an attempt's result is unknown; reconciling
    RETRYABLE = "RETRYABLE"  # verified that no effect exists; a controlled retry is allowed
    DISCREPANCY = "DISCREPANCY"  # an unintended effect is live; recovery in progress
    NEEDS_REVIEW = "NEEDS_REVIEW"  # held for a human
    COMPLETED = "COMPLETED"  # exactly the intended effect is verified at the provider
    REVOKED = "REVOKED"  # authorization withdrawn before any effect
    CLOSED = "CLOSED"  # closed by a reviewer


TERMINAL_STATES = frozenset({IntentState.REVOKED, IntentState.CLOSED})

# Every legal state change. Derived states that are not listed here are bugs.
TRANSITIONS: dict[IntentState, frozenset[IntentState]] = {
    IntentState.AUTHORIZED: frozenset({IntentState.IN_FLIGHT, IntentState.REVOKED, IntentState.NEEDS_REVIEW}),
    IntentState.RETRYABLE: frozenset({IntentState.IN_FLIGHT, IntentState.NEEDS_REVIEW, IntentState.REVOKED}),
    IntentState.IN_FLIGHT: frozenset(
        {
            IntentState.COMPLETED,
            IntentState.PENDING_SETTLEMENT,
            IntentState.OUTCOME_UNKNOWN,
            IntentState.RETRYABLE,
            IntentState.DISCREPANCY,
            IntentState.NEEDS_REVIEW,
        }
    ),
    IntentState.PENDING_SETTLEMENT: frozenset(
        {
            IntentState.COMPLETED,
            IntentState.OUTCOME_UNKNOWN,
            IntentState.DISCREPANCY,
            IntentState.RETRYABLE,
            IntentState.NEEDS_REVIEW,
        }
    ),
    IntentState.OUTCOME_UNKNOWN: frozenset(
        {
            IntentState.COMPLETED,
            IntentState.PENDING_SETTLEMENT,
            IntentState.RETRYABLE,
            IntentState.DISCREPANCY,
            IntentState.NEEDS_REVIEW,
        }
    ),
    IntentState.DISCREPANCY: frozenset(
        {
            IntentState.RETRYABLE,
            IntentState.COMPLETED,
            IntentState.PENDING_SETTLEMENT,
            IntentState.OUTCOME_UNKNOWN,
            IntentState.NEEDS_REVIEW,
        }
    ),
    # A completed intent is reopened if a late duplicate or mismatch is discovered.
    IntentState.COMPLETED: frozenset({IntentState.DISCREPANCY, IntentState.NEEDS_REVIEW}),
    IntentState.NEEDS_REVIEW: frozenset(
        {
            IntentState.COMPLETED,
            IntentState.PENDING_SETTLEMENT,
            IntentState.OUTCOME_UNKNOWN,
            IntentState.RETRYABLE,
            IntentState.CLOSED,
            IntentState.DISCREPANCY,
        }
    ),
    IntentState.REVOKED: frozenset(),
    IntentState.CLOSED: frozenset(),
}


class IllegalTransition(RuntimeError):
    pass


def check_transition(current: IntentState, target: IntentState, *, permissive: bool = False) -> None:
    if current == target or permissive:
        return
    if target not in TRANSITIONS[current]:
        raise IllegalTransition(f"{current} -> {target} is not a legal intent transition")


class Decision(StrEnum):
    APPROVED = "APPROVED"  # gateway will execute
    REJECTED = "REJECTED"  # proposal does not match the authorization / not permitted
    DUPLICATE = "DUPLICATE"  # intent already fulfilled; existing effect returned
    IN_PROGRESS = "IN_PROGRESS"  # an attempt is in flight or being reconciled
    HELD = "HELD"  # intent is held for human review


class AttemptStatus(StrEnum):
    SUBMITTING = "SUBMITTING"  # persisted before the provider call
    ACKNOWLEDGED = "ACKNOWLEDGED"  # provider returned (or reconciliation found) a transaction
    UNKNOWN = "UNKNOWN"  # no response; outcome undetermined
    NO_EFFECT = "NO_EFFECT"  # verified that nothing executed
    REJECTED = "REJECTED"  # provider rejected definitively


UNRESOLVED_ATTEMPTS = frozenset({AttemptStatus.SUBMITTING, AttemptStatus.UNKNOWN})


class ProviderStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


LIVE_PROVIDER_STATUSES = frozenset({ProviderStatus.PENDING, ProviderStatus.COMPLETED})


class EffectClass(StrEnum):
    INTENDED = "INTENDED"  # matches the authorized operation exactly
    DUPLICATE = "DUPLICATE"  # matches, but another intended effect is already live
    MISMATCH = "MISMATCH"  # wrong order / customer / amount / currency / operation


class ReviewReason(StrEnum):
    UNRESOLVABLE_OUTCOME = "UNRESOLVABLE_OUTCOME"
    IRREVERSIBLE_DISCREPANCY = "IRREVERSIBLE_DISCREPANCY"
    CANCEL_REJECTED = "CANCEL_REJECTED"
    CANCEL_UNVERIFIED = "CANCEL_UNVERIFIED"
    ATTEMPT_BUDGET_EXHAUSTED = "ATTEMPT_BUDGET_EXHAUSTED"


class ReviewResolution(StrEnum):
    CONFIRMED_COMPLETED = "CONFIRMED_COMPLETED"  # reviewer verified the intended effect
    CONFIRMED_NO_EFFECT = "CONFIRMED_NO_EFFECT"  # reviewer verified nothing executed; retry allowed
    MANUALLY_REMEDIATED = "MANUALLY_REMEDIATED"  # discrepancy fixed outside the system
    CLOSED_UNFULFILLED = "CLOSED_UNFULFILLED"  # give up on the intent


def cancellation_policy(operation: Operation, status: ProviderStatus) -> bool:
    """
    Whether the gateway may try to reverse a live effect through the provider API.

    Refunds can only be cancelled while pending. Authorization holds can be voided
    while pending or authorized. Anything else must be escalated.
    """
    if status not in LIVE_PROVIDER_STATUSES:
        return False
    if operation == Operation.REFUND:
        return status == ProviderStatus.PENDING
    return True
