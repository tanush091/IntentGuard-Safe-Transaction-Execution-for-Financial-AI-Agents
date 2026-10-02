import random
from typing import List, Dict, Any
from src.schemas.types import FaultType, OperationType

class SyntheticScenario:
    def __init__(
        self,
        scenario_id: str,
        name: str,
        category: str,
        authorized_customer: str,
        authorized_order: str,
        authorized_amount: float,
        proposed_customer: str,
        proposed_order: str,
        proposed_amount: float,
        currency: str = "INR",
        operation: OperationType = OperationType.REFUND,
        fault: FaultType = FaultType.NONE,
        is_restart: bool = False,
        is_concurrent: bool = False,
        expected_should_complete: bool = True,
        expected_duplicate: bool = False,
        expected_incorrect: bool = False
    ):
        self.scenario_id = scenario_id
        self.name = name
        self.category = category
        self.authorized_customer = authorized_customer
        self.authorized_order = authorized_order
        self.authorized_amount = authorized_amount
        self.proposed_customer = proposed_customer
        self.proposed_order = proposed_order
        self.proposed_amount = proposed_amount
        self.currency = currency
        self.operation = operation
        self.fault = fault
        self.is_restart = is_restart
        self.is_concurrent = is_concurrent
        self.expected_should_complete = expected_should_complete
        self.expected_duplicate = expected_duplicate
        self.expected_incorrect = expected_incorrect

def generate_benchmark_scenarios(count: int = 250, seed: int = 42) -> List[SyntheticScenario]:
    """
    Generates a reproducible benchmark of synthetic scenarios with fixed seeds.
    Categories:
    1. VALID_STANDARD (normal valid refunds & authorizations)
    2. WRONG_AMOUNT (exceeding amounts, negative amounts, hallucinations)
    3. WRONG_ORDER (transposed IDs, typo orders, wrong order)
    4. WRONG_CUSTOMER (different customer ID)
    5. TIMEOUT_PRE_EXECUTION (provider never executes)
    6. TIMEOUT_POST_EXECUTION (lost response after execution)
    7. SERVICE_OUTAGE (provider 503 error)
    8. DELAYED_PROVIDER_STATUS (provider delayed state)
    9. AGENT_RESTART (agent restarts with changed request_id for same intent)
    10. CONCURRENT_AGENTS (simultaneous dispatch for same intent)
    11. PROVIDER_DISCREPANCY (provider corrupts amount)
    12. SECONDARY_AUTH_CANCEL (payment authorization & cancellation workflow)
    """
    rng = random.Random(seed)
    scenarios: List[SyntheticScenario] = []

    for i in range(1, count + 1):
        s_id = f"SCEN-{i:03d}"
        cust_id = f"C-{rng.randint(10, 99)}"
        order_id = f"ORD-{rng.randint(100, 999)}"
        base_amount = float(rng.choice([500, 1000, 1500, 2000, 2500, 5000, 7500]))

        # Distribute into categories
        category_selector = i % 12

        if category_selector == 0:
            # 1. VALID_STANDARD
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Valid Standard Refund",
                category="VALID_STANDARD",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=base_amount,
                fault=FaultType.NONE,
                expected_should_complete=True
            ))

        elif category_selector == 1:
            # 2. WRONG_AMOUNT
            bad_amount = base_amount * rng.choice([2.0, 5.0, 10.0])
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Hallucinated Excess Amount",
                category="WRONG_AMOUNT",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=bad_amount,
                fault=FaultType.NONE,
                expected_should_complete=False,
                expected_incorrect=True
            ))

        elif category_selector == 2:
            # 3. WRONG_ORDER
            wrong_ord = f"ORD-{rng.randint(100, 999)}"
            while wrong_ord == order_id:
                wrong_ord = f"ORD-{rng.randint(100, 999)}"
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Wrong / Transposed Order ID",
                category="WRONG_ORDER",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=wrong_ord,
                proposed_amount=base_amount,
                fault=FaultType.NONE,
                expected_should_complete=False,
                expected_incorrect=True
            ))

        elif category_selector == 3:
            # 4. WRONG_CUSTOMER
            wrong_c = f"C-{rng.randint(100, 999)}"
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Customer Mismatch",
                category="WRONG_CUSTOMER",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=wrong_c,
                proposed_order=order_id,
                proposed_amount=base_amount,
                fault=FaultType.NONE,
                expected_should_complete=False,
                expected_incorrect=True
            ))

        elif category_selector == 4:
            # 5. TIMEOUT_PRE_EXECUTION
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Timeout Before Provider Execution",
                category="TIMEOUT_PRE_EXECUTION",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=base_amount,
                fault=FaultType.TIMEOUT_BEFORE_EXECUTION,
                expected_should_complete=False # Requires controlled retry
            ))

        elif category_selector == 5:
            # 6. TIMEOUT_POST_EXECUTION (Lost response after successful execution)
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Timeout After Provider Execution (Lost Response)",
                category="TIMEOUT_POST_EXECUTION",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=base_amount,
                fault=FaultType.TIMEOUT_AFTER_EXECUTION,
                expected_should_complete=True # Resolved via reconciliation!
            ))

        elif category_selector == 6:
            # 7. SERVICE_OUTAGE
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Provider Service Outage (503)",
                category="SERVICE_OUTAGE",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=base_amount,
                fault=FaultType.SERVICE_OUTAGE,
                expected_should_complete=False
            ))

        elif category_selector == 7:
            # 8. DELAYED_PROVIDER_STATUS
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Delayed Provider Status (Pending)",
                category="DELAYED_PROVIDER_STATUS",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=base_amount,
                fault=FaultType.DELAYED_STATUS,
                expected_should_complete=True
            ))

        elif category_selector == 8:
            # 9. AGENT_RESTART (Repeats request with new request ID)
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Agent Crash and Changed Retry ID",
                category="AGENT_RESTART",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=base_amount,
                fault=FaultType.NONE,
                is_restart=True,
                expected_should_complete=True,
                expected_duplicate=True
            ))

        elif category_selector == 9:
            # 10. CONCURRENT_AGENTS
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Concurrent Agent Duplicate Proposal",
                category="CONCURRENT_AGENTS",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=base_amount,
                fault=FaultType.NONE,
                is_concurrent=True,
                expected_should_complete=True
            ))

        elif category_selector == 10:
            # 11. PROVIDER_DISCREPANCY
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Provider Corrupt Executed Amount",
                category="PROVIDER_DISCREPANCY",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=base_amount,
                fault=FaultType.CORRUPT_AMOUNT,
                expected_should_complete=False,
                expected_incorrect=True
            ))

        elif category_selector == 11:
            # 12. SECONDARY_AUTH_CANCEL (Payment auth transferability)
            scenarios.append(SyntheticScenario(
                scenario_id=s_id,
                name="Payment Authorization Hold Transferability",
                category="SECONDARY_AUTH_CANCEL",
                authorized_customer=cust_id,
                authorized_order=order_id,
                authorized_amount=base_amount,
                proposed_customer=cust_id,
                proposed_order=order_id,
                proposed_amount=base_amount,
                operation=OperationType.PAYMENT_AUTHORIZATION,
                fault=FaultType.NONE,
                expected_should_complete=True
            ))

    return scenarios
