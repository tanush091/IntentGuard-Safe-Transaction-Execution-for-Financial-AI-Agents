"""
Domain vocabulary and the intent state machine.

An *intent* is the business request an operator authorized. It is distinct from
an agent *proposal* (what the agent asked for), an *attempt* (one provider API
call made by the gateway), and an *effect* (a transaction actually observed at
the provider). Intent state is derived from attempts and effects, and every
change is checked against TRANSITIONS.

Names follow docs/API.md. Proposal-level outcomes (PROPOSED, VALIDATED, REJECTED,
BLOCKED) are ProposalStatus values, not intent states: a rejected proposal leaves
the intent AUTHORIZED so a corrected proposal can still be accepted.
"""

from __future__ import annotations

from enum import StrEnum


class Operation(StrEnum):
    REFUND = "REFUND"
    PAYMENT_AUTHORIZATION = "PAYMENT_AUTHORIZATION"


class IntentState(StrEnum):
    AUTHORIZED = "AUTHORIZED"  # approved; no live attempt or effect (a rejected proposal leaves it here)
    IN_FLIGHT = "IN_FLIGHT"  # an attempt is reserved and being submitted
    EXECUTING = "EXECUTING"  # the intended effect exists at the provider and is still pending
    UNKNOWN = "UNKNOWN"  # an attempt's result is unknown; reconciling
    RECONCILING = "RECONCILING"  # reconciled to no live effect; a controlled retry or a new proposal is allowed
    DISCREPANCY = "DISCREPANCY"  # an unintended effect is live; recovery in progress
    CANCEL_REQUESTED = "CANCEL_REQUESTED"  # an operator asked to cancel; live effects are being cancelled
    ESCALATED = "ESCALATED"  # held for a human (an open review case exists)
    COMPLETED = "COMPLETED"  # exactly the intended effect is verified at the provider
    CANCELLED = "CANCELLED"  # cancelled with no live effect (verified at the provider)
    CLOSED = "CLOSED"  # written off by a reviewer


TERMINAL_STATES = frozenset({IntentState.CANCELLED, IntentState.CLOSED})

# Every legal state change. Derived states that are not listed here are bugs.
TRANSITIONS: dict[IntentState, frozenset[IntentState]] = {
    IntentState.AUTHORIZED: frozenset({IntentState.IN_FLIGHT, IntentState.CANCELLED, IntentState.ESCALATED}),
    IntentState.RECONCILING: frozenset({IntentState.IN_FLIGHT, IntentState.ESCALATED, IntentState.CANCELLED}),
    IntentState.IN_FLIGHT: frozenset(
        {
            IntentState.COMPLETED,
            IntentState.EXECUTING,
            IntentState.UNKNOWN,
            IntentState.RECONCILING,
            IntentState.DISCREPANCY,
            IntentState.ESCALATED,
        }
    ),
    IntentState.EXECUTING: frozenset(
        {
            IntentState.COMPLETED,
            IntentState.UNKNOWN,
            IntentState.DISCREPANCY,
            IntentState.RECONCILING,
            IntentState.ESCALATED,
            IntentState.CANCEL_REQUESTED,
        }
    ),
    IntentState.UNKNOWN: frozenset(
        {
            IntentState.COMPLETED,
            IntentState.EXECUTING,
            IntentState.RECONCILING,
            IntentState.DISCREPANCY,
            IntentState.ESCALATED,
        }
    ),
    IntentState.DISCREPANCY: frozenset(
        {
            IntentState.RECONCILING,
            IntentState.COMPLETED,
            IntentState.EXECUTING,
            IntentState.UNKNOWN,
            IntentState.ESCALATED,
        }
    ),
    # A completed intent is reopened if a late duplicate or mismatch is discovered. A completed
    # authorization hold can still be voided, so it can also move to CANCEL_REQUESTED.
    IntentState.COMPLETED: frozenset({IntentState.DISCREPANCY, IntentState.ESCALATED, IntentState.CANCEL_REQUESTED}),
    IntentState.CANCEL_REQUESTED: frozenset({IntentState.CANCELLED, IntentState.ESCALATED}),
    IntentState.ESCALATED: frozenset(
        {
            IntentState.COMPLETED,
            IntentState.EXECUTING,
            IntentState.UNKNOWN,
            IntentState.RECONCILING,
            IntentState.CLOSED,
            IntentState.DISCREPANCY,
            IntentState.CANCEL_REQUESTED,
            IntentState.CANCELLED,
        }
    ),
    IntentState.CANCELLED: frozenset(),
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
    ALLOW = "ALLOW"  # gateway will execute
    REJECT = "REJECT"  # proposal does not match the authorization / not permitted
    DUPLICATE = "DUPLICATE"  # the gateway already owns this intent (completed, executing or in progress)
    HOLD_FOR_REVIEW = "HOLD_FOR_REVIEW"  # held for a human, attempt budget used up, or kill switch on


class ProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"  # recorded, not yet evaluated (only seen inside the deciding transaction)
    VALIDATED = "VALIDATED"  # all checks passed; executed (decision ALLOW)
    REJECTED = "REJECTED"  # does not match the authorization (decision REJECT)
    BLOCKED = "BLOCKED"  # valid, but blocked by intent state or policy (DUPLICATE, HOLD_FOR_REVIEW)


def proposal_status(decision: Decision) -> ProposalStatus:
    if decision == Decision.ALLOW:
        return ProposalStatus.VALIDATED
    if decision == Decision.REJECT:
        return ProposalStatus.REJECTED
    return ProposalStatus.BLOCKED


class AttemptStatus(StrEnum):
    SUBMITTING = "SUBMITTING"  # persisted before the provider call
    SUCCEEDED = "SUCCEEDED"  # provider returned (or reconciliation found) a transaction
    UNKNOWN = "UNKNOWN"  # no response; outcome undetermined
    RECONCILED = "RECONCILED"  # outcome was unknown; verified that nothing executed
    FAILED = "FAILED"  # provider rejected definitively; nothing executed


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
    INVESTIGATOR_ESCALATION = "INVESTIGATOR_ESCALATION"


class ReviewResolution(StrEnum):
    ACCEPTED_AS_IS = "ACCEPTED_AS_IS"  # the verified intended effect stands as the outcome
    REFUND_RECOVERED_OUT_OF_BAND = "REFUND_RECOVERED_OUT_OF_BAND"  # wrong effect handled outside the system
    WRITTEN_OFF = "WRITTEN_OFF"  # give up on the intent
    CONFIRMED_NO_EFFECT = "CONFIRMED_NO_EFFECT"  # reviewer verified nothing executed; retry allowed
    OTHER = "OTHER"  # case closed with a note; the intent is re-derived unchanged


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
