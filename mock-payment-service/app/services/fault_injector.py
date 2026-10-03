"""
Fault Injection Engine for Mock Payment Simulator.
Simulates deterministic network drops, 503 outages, delayed visibility, and lost responses.
"""

from typing import Dict, Any, Optional
import time


class FaultInjector:
    def __init__(self):
        self.active_faults: Dict[str, Dict[str, Any]] = {}

    def configure_fault(self, fault_type: str, target_order_id: Optional[str] = None, delay_seconds: float = 0.0):
        key = target_order_id or "__global__"
        self.active_faults[key] = {
            "fault_type": fault_type.upper(),
            "delay_seconds": delay_seconds,
            "configured_at": time.time()
        }

    def should_trigger(self, fault_type: str, order_id: Optional[str] = None) -> bool:
        target_type = fault_type.upper()
        # Check order-specific fault
        if order_id and order_id in self.active_faults:
            if self.active_faults[order_id]["fault_type"] == target_type:
                return True
        # Check global fault
        if "__global__" in self.active_faults:
            if self.active_faults["__global__"]["fault_type"] == target_type:
                return True
        return False

    def get_delay(self, order_id: Optional[str] = None) -> float:
        if order_id and order_id in self.active_faults:
            return self.active_faults[order_id].get("delay_seconds", 0.0)
        if "__global__" in self.active_faults:
            return self.active_faults["__global__"].get("delay_seconds", 0.0)
        return 0.0

    def reset(self):
        self.active_faults.clear()

    def get_status(self) -> Dict[str, Any]:
        return {"active_fault_count": len(self.active_faults), "faults": self.active_faults}


fault_injector = FaultInjector()
