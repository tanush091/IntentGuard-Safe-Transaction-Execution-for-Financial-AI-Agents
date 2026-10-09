"""
investigate(): build evidence, classify, gate, store (prompt and raw output included, for audit).
apply_investigation(): re-check the gate against fresh evidence (state may have moved on), then run
the action through the engine. A refused action changes nothing.
"""

from __future__ import annotations

from typing import Any

from intentguard.domain import IntentState, Operation
from intentguard.engine import ConflictError, IntentGuard, NotFound
from intentguard.models import Intent, Investigation
from investigator.classifier import Classifier, InvalidOutput
from investigator.evidence import EXCEPTION_STATES, build_bundle
from investigator.policy import gate


class InvestigatorOutputRejected(Exception):
    def __init__(self, investigation_id: int, reason: str):
        super().__init__(reason)
        self.investigation_id, self.reason = investigation_id, reason


def _store(guard: IntentGuard, **fields: Any) -> int:
    with guard.session() as s, s.begin():
        inv = Investigation(**fields)
        s.add(inv)
        s.flush()
        return inv.id


def investigate(guard: IntentGuard, intent_id: str, actor: str, classifier: Classifier) -> int:
    """Run one investigation. Returns its id. Raises InvestigatorOutputRejected for invalid output."""
    state = guard._state(intent_id)
    if state not in EXCEPTION_STATES:
        raise ConflictError(f"intent is {state.value}; only exceptions are investigated "
                            f"({', '.join(sorted(s.value for s in EXCEPTION_STATES))})", "NOT_AN_EXCEPTION")
    bundle = build_bundle(guard, intent_id)
    now = guard.clock.now()
    try:
        result = classifier.classify(bundle)
    except InvalidOutput as exc:
        inv_id = _store(guard, intent_id=intent_id, intent_state=state.value, valid_output=False,
                        classification="UNKNOWN", summary=f"rejected output: {exc.reason}"[:800], evidence_refs=[],
                        recommended_action="ESCALATE", policy_permitted=False, policy_rule="invalid_output",
                        model=getattr(classifier, "model_name", "unknown"), prompt="(see evidence)",
                        raw_output=exc.raw[:20000], created_by=actor, created_at=now)
        guard.record_audit("investigation.rejected_output", actor, intent_id, investigation_id=inv_id,
                           reason=exc.reason)
        raise InvestigatorOutputRejected(inv_id, exc.reason) from exc
    verdict = gate(result.recommended_action, bundle.facts)
    inv_id = _store(guard, intent_id=intent_id, intent_state=state.value, valid_output=True,
                    classification=result.classification, summary=result.summary,
                    evidence_refs=result.evidence_refs, recommended_action=result.recommended_action,
                    policy_permitted=verdict.permitted, policy_rule=verdict.rule, model=result.model,
                    prompt=result.prompt[:20000], raw_output=result.raw_output[:20000],
                    tokens_in=result.tokens_in, tokens_out=result.tokens_out, created_by=actor, created_at=now)
    guard.record_audit("investigation.created", actor, intent_id, investigation_id=inv_id,
                       classification=result.classification, recommended_action=result.recommended_action,
                       permitted=verdict.permitted, rule=verdict.rule, model=result.model)
    return inv_id


def apply_investigation(guard: IntentGuard, investigation_id: int, actor: str) -> dict[str, Any]:
    with guard.session() as s:
        inv = s.get(Investigation, investigation_id)
        if inv is None:
            raise NotFound(f"investigation {investigation_id} not found")
        if inv.applied_at is not None:
            raise ConflictError("this recommendation was already applied", "ALREADY_APPLIED")
        if not inv.valid_output:
            raise ConflictError("the investigator output was rejected; nothing can be applied", "POLICY_REFUSED",
                                rule="invalid_output")
        intent_id, action = inv.intent_id, inv.recommended_action
        operation = Operation(s.get(Intent, intent_id).operation)  # type: ignore[union-attr]

    bundle = build_bundle(guard, intent_id)  # fresh evidence: the state may have changed since
    verdict = gate(action, bundle.facts)
    if not verdict.permitted:
        guard.record_audit("investigation.apply_refused", actor, intent_id, investigation_id=investigation_id,
                           action=action, rule=verdict.rule)
        raise ConflictError(f"policy does not permit {action} now ({verdict.rule})", "POLICY_REFUSED",
                            rule=verdict.rule)

    if action == "MARK_COMPLETED":
        state = guard._state(intent_id)
        for ref in bundle.facts.matching_live_refs:
            state, _ = guard.observe(intent_id, operation, ref.split(":", 1)[1])
    elif action == "WAIT_AND_RECHECK":
        state = guard.schedule_recheck(intent_id, actor)
    elif action == "CONTROLLED_RETRY":
        state = guard.retry_now(intent_id)
    elif action == "CANCEL_PENDING":
        guard.recover(intent_id)
        state = guard._drive(intent_id)
    else:  # ESCALATE
        state = guard.escalate(intent_id, actor, investigation_id=investigation_id)

    outcome = f"{action} -> {IntentState(state).value}"
    with guard.session() as s, s.begin():
        inv = s.get(Investigation, investigation_id)
        assert inv is not None
        inv.applied_at, inv.applied_by, inv.apply_outcome = guard.clock.now(), actor, outcome
    guard.record_audit("investigation.applied", actor, intent_id, investigation_id=investigation_id,
                       action=action, rule=verdict.rule, intent_state=IntentState(state).value)
    return {"investigation_id": investigation_id, "action": action, "rule": verdict.rule,
            "intent_state": IntentState(state).value}
