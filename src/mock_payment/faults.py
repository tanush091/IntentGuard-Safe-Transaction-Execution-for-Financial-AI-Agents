import time
import asyncio
from typing import Optional, Dict
from pydantic import BaseModel
from src.schemas.types import FaultType

class FaultConfiguration(BaseModel):
    fault_type: FaultType = FaultType.NONE
    delay_seconds: float = 0.0
    active: bool = True
    target_order_id: Optional[str] = None
    target_intent_id: Optional[str] = None

class FaultEngine:
    def __init__(self):
        self._global_fault: Optional[FaultConfiguration] = None
        self._order_faults: Dict[str, FaultConfiguration] = {}

    def set_global_fault(self, fault: FaultConfiguration):
        self._global_fault = fault

    def set_order_fault(self, order_id: str, fault: FaultConfiguration):
        self._order_faults[order_id] = fault

    def clear_faults(self):
        self._global_fault = None
        self._order_faults.clear()

    def get_fault_for_order(self, order_id: Optional[str] = None, requested_fault: Optional[FaultType] = None) -> FaultConfiguration:
        if requested_fault and requested_fault != FaultType.NONE:
            return FaultConfiguration(fault_type=requested_fault, active=True)
        if order_id and order_id in self._order_faults:
            return self._order_faults[order_id]
        if self._global_fault and self._global_fault.active:
            return self._global_fault
        return FaultConfiguration(fault_type=FaultType.NONE, active=False)

fault_engine = FaultEngine()
