"""
Active External-State Reconciliation Service for IntentGuard.
Reconciles UNKNOWN outcomes before permitting retries or marking completion.
"""

from typing import Optional, Dict, Any, List
import uuid
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.intent import IntentModel
from backend.app.models.attempt import AttemptModel
from backend.app.models.effect import EffectModel
from backend.app.services.audit_service import AuditService
from backend.app.services.recovery_service import RecoveryService
from backend.app.services.http_client import send_payment_request
from backend.app.state_machine.transaction_state_machine import TransactionStateMachine


class ReconciliationService:
    @staticmethod
    def reconcile(
        db: Session,
        intent: IntentModel,
        attempt: AttemptModel
    ) -> Dict[str, Any]:
        """
        Execute the 8-step active reconciliation protocol against the mock payment provider.
        """
        if TransactionStateMachine.is_legal(intent.current_state, "RECONCILING"):
            intent.current_state = "RECONCILING"
            db.commit()

        AuditService.record_event(
            db=db,
            intent_id=intent.id,
            attempt_id=attempt.id,
            event_type="RECONCILIATION_STARTED",
            decision="RECONCILE",
            reason=f"Attempt {attempt.attempt_number} yielded UNKNOWN outcome. Querying external provider ledger."
        )

        provider_effects: List[Dict[str, Any]] = []

        query_url = f"{settings.PAYMENT_SERVICE_URL}/refunds"
        try:
            resp = send_payment_request("GET", query_url, params={"order_id": intent.order_id})
            if resp.status_code == 200:
                provider_effects = resp.json()
        except Exception as e:
            RecoveryService.escalate(
                db=db,
                intent=intent,
                reason=f"Provider unreachable during reconciliation sweep: {e}",
                severity="CRITICAL"
            )
            return {"outcome": "ESCALATED", "reason": "Provider unreachable during reconciliation"}

        matching_effect: Optional[Dict[str, Any]] = None
        corrupted_effect: Optional[Dict[str, Any]] = None

        for eff in provider_effects:
            amount_matches = abs(float(eff.get("amount", 0)) - float(intent.authorized_amount)) < 0.001
            currency_matches = str(eff.get("currency", "")).upper() == intent.currency.upper()
            status_completed = eff.get("status") in ["COMPLETED", "SETTLED"]

            if amount_matches and currency_matches and status_completed:
                matching_effect = eff
                break
            elif not amount_matches:
                corrupted_effect = eff

        if matching_effect:
            prov_ref = matching_effect.get("id") or matching_effect.get("provider_reference")
            attempt.status = "COMPLETED"
            attempt.provider_reference = prov_ref
            
            existing_local = db.query(EffectModel).filter(EffectModel.provider_reference == prov_ref).first()
            if not existing_local:
                effect_record = EffectModel(
                    id=f"eff_{uuid.uuid4().hex[:10]}",
                    intent_id=intent.id,
                    attempt_id=attempt.id,
                    provider_reference=prov_ref,
                    effect_type=intent.operation_type,
                    order_id=intent.order_id,
                    amount=intent.authorized_amount,
                    currency=intent.currency,
                    status="COMPLETED"
                )
                db.add(effect_record)

            intent.current_state = "COMPLETED"
            db.commit()

            AuditService.record_event(
                db=db,
                intent_id=intent.id,
                attempt_id=attempt.id,
                event_type="RECONCILIATION_VERIFIED",
                decision="COMPLETED",
                reason=(
                    f"Reconciliation verified refund settled at provider (Ref: {prov_ref}). "
                    f"Resolved without duplicate retry."
                )
            )
            return {"outcome": "COMPLETED", "provider_reference": prov_ref}

        elif corrupted_effect:
            prov_ref = corrupted_effect.get("id") or corrupted_effect.get("provider_reference")
            AuditService.record_event(
                db=db,
                intent_id=intent.id,
                attempt_id=attempt.id,
                event_type="RECONCILIATION_MISMATCH",
                decision="RECOVERY_REQUIRED",
                reason=f"Observed provider effect amount mismatch: {corrupted_effect.get('amount')}"
            )
            cancelled = RecoveryService.attempt_cancellation(db, intent, prov_ref)
            if cancelled:
                return {"outcome": "CANCELLED", "provider_reference": prov_ref}
            else:
                return {"outcome": "ESCALATED", "provider_reference": prov_ref}

        else:
            intent.current_state = "RETRY_ALLOWED"
            db.commit()

            AuditService.record_event(
                db=db,
                intent_id=intent.id,
                attempt_id=attempt.id,
                event_type="RECONCILIATION_ZERO_EFFECT",
                decision="RETRY_ALLOWED",
                reason="Provider confirms zero records for this order. Safe controlled retry permitted."
            )
            return {"outcome": "RETRY_ALLOWED", "reason": "No provider effect observed"}
