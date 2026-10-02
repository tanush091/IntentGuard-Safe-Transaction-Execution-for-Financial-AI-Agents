"""
Fault Injection API Endpoints for Mock Payment Simulator.
Allows test suites and benchmarks to trigger deterministic network failures.
"""

from typing import Dict, Any
from fastapi import APIRouter
from ..schemas import FaultConfigRequest
from ..services.fault_injector import fault_injector

router = APIRouter(prefix="/faults", tags=["Fault Injection"])


@router.post("/configure")
def configure_fault(req: FaultConfigRequest) -> Dict[str, Any]:
    """Configure a simulated fault injection behavior."""
    fault_injector.configure_fault(
        fault_type=req.fault_type,
        target_order_id=req.target_order_id,
        delay_seconds=req.delay_seconds
    )
    return {"status": "configured", "fault": req.dict()}


@router.post("/reset")
def reset_faults() -> Dict[str, Any]:
    """Reset all active faults to default healthy behavior."""
    fault_injector.reset()
    return {"status": "reset", "active_fault_count": 0}


@router.get("")
def list_faults() -> Dict[str, Any]:
    """List currently active faults."""
    return fault_injector.get_status()
