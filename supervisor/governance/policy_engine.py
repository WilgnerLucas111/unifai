#!/usr/bin/env python3
"""
GovernancePolicyEngine - Machine-Checkable Governance Conditions (Constitution v0.3)

This module enforces deterministic, auditable governance rules for the Supervisor runtime.
All decisions are mathematically verifiable and traceable to specific policy thresholds.

No heuristics, no ambiguity, no agent negotiation: only explicit conditions and thresholds.
This is the World Physics layer—guaranteed enforcement mechanism for Rule 0, Rule 5, Rule 6.

Author: Architect Integration Engineer (UnifAI Alpha)
"""

from typing import Dict, Any, List


class GovernancePolicyEngine:
    """
    Central policy enforcement engine for UnifAI Governance Constitution v0.3.
    
    This class encapsulates all machine-checkable governance conditions that guard:
    - Supervisor execution gate (pre-execution validation)
    - Neo risk evaluation (deterministic action thresholds)
    - Keyman authorization conditions (mandatory field validation)
    
    PHILOSOPHY:
    -----------
    Governance is NOT negotiable and NOT fuzzy. Every decision must be traceable to 
    explicit numerical thresholds or presence/absence of mandatory fields. This engine
    centralizes all policy logic so it can be audited, tested, and updated atomically.
    
    CONSTITUTION v0.3 PRINCIPLES:
    - Rule 0 (Secret Sovereignty): trace_id mandatory, no raw secrets in spec
    - Rule 1 (Deterministic Action): Risk score → deterministic action (warn/deny/fuse/kill)
    - Rule 5 (Fuse Determinism): Fuse threshold guaranteed; never negotiable
    - Rule 6 (Denial Signals): All denials are threat signals routed to Neo
    
    RISK SCORE THRESHOLDS (Neo Guardian):
    - risk_score < 1: Allow execution (ALLOW)
    - risk_score >= 1: Warn only (WARN)
    - risk_score >= 3: Deny execution (DENY)
    - risk_score >= 5: Trip fuse for immediate termination (FUSE)
    - risk_score >= 8: Force kill without grace period (KILL)
    
    All conditions are mathematical; all violations are security signals.
    """
    
    # ==================== RISK SCORE THRESHOLDS ====================
    # These constants define the deterministic action boundaries.
    # They are immutable and form the World Physics of UnifAI.
    
    RISK_THRESHOLD_WARN = 1
    """Minimum risk score to trigger WARN action. Below this = ALLOW."""
    
    RISK_THRESHOLD_DENY = 3
    """Minimum risk score to trigger DENY action."""
    
    RISK_THRESHOLD_FUSE = 5
    """Minimum risk score to trip the Fuse (immediate agent termination)."""
    
    RISK_THRESHOLD_KILL = 8
    """Minimum risk score to force KILL without grace period."""
    
    # ==================== EXECUTION PRECONDITIONS ====================
    # These are mandatory fields/conditions that MUST be present for any task
    # to proceed past the Supervisor boundary.
    
    REQUIRED_EXECUTION_FIELDS = {
        "trace_id",  # Mandatory: audit trail identification
        "architect_instruction",  # Mandatory: explicit authorization from human
        "ledger_entry",  # Mandatory: incident/action ledger for accountability
    }
    """Required fields in task spec for execution. Absence = immediate DENY."""
    
    # ==================== KEYMAN AUTHORIZATION CONDITIONS ====================
    # These are mandatory fields/conditions for Keyman to issue any grant.
    # Missing ANY of these = automatic DENY (SKILL keyman section 8).
    
    REQUIRED_KEYMAN_FIELDS = {
        "trace_id",  # Mandatory: link denial to audit trail
        "scope",  # Mandatory: capability scope (e.g., "db_read", "api_write")
        "ttl_seconds",  # Mandatory: time-to-live for ephemeral grant
    }
    """Required fields in Keyman request. Absence = automatic block_task."""
    
    # ==================== ACTION STRINGS ====================
    # These are the deterministic outputs of policy evaluation.
    
    ACTION_ALLOW = "ALLOW"
    """Risk < 1: execution permitted."""
    
    ACTION_WARN = "WARN"
    """Risk [1, 3): warn but allow (audit signal)."""
    
    ACTION_DENY = "DENY"
    """Risk [3, 5): deny execution (threat detected)."""
    
    ACTION_FUSE = "FUSE"
    """Risk [5, 8): trip fuse (immediate termination)."""
    
    ACTION_KILL = "KILL"
    """Risk >= 8: force kill without grace (catastrophic threat)."""
    
    # ==================== KEYMAN DECISIONS ====================
    # These are the deterministic outputs of Keyman policy evaluation.
    
    KEYMAN_DECISION_ALLOW = "issue_grant"
    """All conditions satisfied: issue ephemeral grant."""
    
    KEYMAN_DECISION_DENY = "block_task"
    """Missing mandatory field or failed condition: automatic deny (fail-secure)."""
    
    KEYMAN_DECISION_QUARANTINE = "quarantine"
    """Threat pattern detected: isolate agent (escalated to Neo)."""
    
    def __init__(self):
        """
        Initialize the Governance Policy Engine.
        
        All thresholds and conditions are loaded at instantiation and immutable
        after construction. This ensures atomic policy updates across the system.
        """
        pass
    
    # ==================== NEO RISK EVALUATION ====================
    
    def evaluate_neo_risk(self, risk_score: int) -> str:
        """
        Deterministic action evaluation based on Neo risk score.
        
        This is the central enforcement point for Neo security decisions. Given a
        numerical risk score (calculated by the Neo Guardian from threat signals),
        this method returns the deterministic action the Supervisor must take.
        
        No heuristics, no interpretation: pure mathematical mapping.
        
        Args:
            risk_score (int): Numerical risk assessment from Neo Guardian.
                              Typically in range [0, 10], but unbounded to handle
                              catastrophic threat scenarios.
        
        Returns:
            str: One of:
                - ACTION_ALLOW ("ALLOW"): risk < 1, safe to proceed
                - ACTION_WARN ("WARN"): risk [1, 3), suspicious but allowed (audit)
                - ACTION_DENY ("DENY"): risk [3, 5), explicit denial (threat signal)
                - ACTION_FUSE ("FUSE"): risk [5, 8), trip fuse (kill agent)
                - ACTION_KILL ("KILL"): risk >= 8, force kill (catastrophic)
        
        Raises:
            ValueError: If risk_score is not a valid integer.
        
        Example:
            >>> engine = GovernancePolicyEngine()
            >>> engine.evaluate_neo_risk(0)
            'ALLOW'
            >>> engine.evaluate_neo_risk(2)
            'WARN'
            >>> engine.evaluate_neo_risk(4)
            'DENY'
            >>> engine.evaluate_neo_risk(6)
            'FUSE'
            >>> engine.evaluate_neo_risk(10)
            'KILL'
        """
        if not isinstance(risk_score, int):
            raise ValueError(f"risk_score must be integer, got {type(risk_score)}")
        
        # Deterministic action mapping (highest threshold first, fail-safe order)
        if risk_score >= self.RISK_THRESHOLD_KILL:
            return self.ACTION_KILL
        elif risk_score >= self.RISK_THRESHOLD_FUSE:
            return self.ACTION_FUSE
        elif risk_score >= self.RISK_THRESHOLD_DENY:
            return self.ACTION_DENY
        elif risk_score >= self.RISK_THRESHOLD_WARN:
            return self.ACTION_WARN
        else:
            return self.ACTION_ALLOW
    
    # ==================== EXECUTION PRECONDITIONS ====================
    
    def check_execution_preconditions(self, spec: Dict[str, Any]) -> bool:
        """
        Validate that a task spec satisfies all Supervisor execution preconditions.
        
        This is the fail-fast gate at the Supervisor boundary. Before any execution
        (tool, LLM, etc.), the task spec must contain ALL mandatory fields defined
        in CONSTITUTION v0.3.
        
        Missing ANY field → immediate DENY (fail-secure).
        
        Args:
            spec (dict): Task specification dictionary loaded from Supervisor task table.
                         Expected keys (mandatory):
                         - "trace_id": str (audit trail identifier)
                         - "architect_instruction": str or bool (explicit human approval)
                         - "ledger_entry": dict or str (incident/action ledger reference)
        
        Returns:
            bool: True if ALL preconditions satisfied, False otherwise (fail-secure).
        
        FAIL-SECURE BEHAVIOR:
        - Missing trace_id → False (no audit trail)
        - Missing architect_instruction → False (no authorization)
        - Missing ledger_entry → False (no accountability)
        - Any field is None or empty string → False
        
        Example:
            >>> engine = GovernancePolicyEngine()
            >>> spec_valid = {
            ...     "trace_id": "audit-001",
            ...     "architect_instruction": "approved",
            ...     "ledger_entry": {"incident_id": "inc-123"}
            ... }
            >>> engine.check_execution_preconditions(spec_valid)
            True
            
            >>> spec_missing_trace = {
            ...     "architect_instruction": "approved",
            ...     "ledger_entry": {"incident_id": "inc-123"}
            ... }
            >>> engine.check_execution_preconditions(spec_missing_trace)
            False
        """
        if not isinstance(spec, dict):
            return False
        
        # Check each mandatory field
        for field in self.REQUIRED_EXECUTION_FIELDS:
            value = spec.get(field)
            
            # Field missing or None = fail-secure
            if value is None:
                return False
            
            # Empty string = fail-secure
            if isinstance(value, str) and not value.strip():
                return False
            
            # Empty collection (dict/list) = fail-secure
            if isinstance(value, (dict, list)) and len(value) == 0:
                return False
        
        # All preconditions satisfied
        return True
    
    def get_missing_execution_preconditions(self, spec: Dict[str, Any]) -> List[str]:
        """
        Identify which execution preconditions are missing (for audit/diagnostics).
        
        Useful for constructing detailed error messages when preconditions fail.
        
        Args:
            spec (dict): Task specification dictionary.
        
        Returns:
            list[str]: List of missing field names. Empty list if all satisfied.
        
        Example:
            >>> engine = GovernancePolicyEngine()
            >>> spec = {"trace_id": "audit-001"}
            >>> engine.get_missing_execution_preconditions(spec)
            ['architect_instruction', 'ledger_entry']
        """
        missing = []
        
        if not isinstance(spec, dict):
            return list(self.REQUIRED_EXECUTION_FIELDS)
        
        for field in self.REQUIRED_EXECUTION_FIELDS:
            value = spec.get(field)
            
            # Missing or invalid
            if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, (dict, list)) and len(value) == 0):
                missing.append(field)
        
        return missing
    
    # ==================== KEYMAN AUTHORIZATION CONDITIONS ====================
    
    def check_keyman_allow_conditions(self, request: Dict[str, Any]) -> bool:
        """
        Validate that a Keyman authorization request satisfies all conditions.
        
        This is the fail-secure gate for capability grants. Before issuing any
        ephemeral grant (Grant ID with TTL), Keyman must validate that the request
        contains ALL mandatory fields and passes all policy conditions.
        
        Missing ANY field → automatic DENY (decision: "block_task") per SKILL keyman section 8.
        
        Args:
            request (dict): Keyman authorization request dictionary.
                           Expected keys (mandatory):
                           - "trace_id": str (link denial to audit trail)
                           - "scope": str (capability scope, e.g., "db_read", "api_write")
                           - "ttl_seconds": int (grant lifetime in seconds, range [1, 3600])
        
        Returns:
            bool: True if ALL Keyman conditions satisfied, False otherwise (fail-secure).
        
        FAIL-SECURE BEHAVIOR:
        - Missing trace_id → False
        - Missing scope → False
        - Missing ttl_seconds → False
        - Any field is None or empty string → False
        - ttl_seconds outside [1, 3600] → False (per SKILL keyman section 4)
        
        Example:
            >>> engine = GovernancePolicyEngine()
            >>> request_valid = {
            ...     "trace_id": "req-001",
            ...     "scope": "db_read",
            ...     "ttl_seconds": 300
            ... }
            >>> engine.check_keyman_allow_conditions(request_valid)
            True
            
            >>> request_missing_ttl = {
            ...     "trace_id": "req-001",
            ...     "scope": "db_read"
            ... }
            >>> engine.check_keyman_allow_conditions(request_missing_ttl)
            False
            
            >>> request_invalid_ttl = {
            ...     "trace_id": "req-001",
            ...     "scope": "db_read",
            ...     "ttl_seconds": 7200  # Exceeds max 3600
            ... }
            >>> engine.check_keyman_allow_conditions(request_invalid_ttl)
            False  # TTL must be capped at 3600 seconds (1 hour)
        """
        if not isinstance(request, dict):
            return False
        
        # Check each mandatory field
        for field in self.REQUIRED_KEYMAN_FIELDS:
            value = request.get(field)
            
            # Field missing or None = fail-secure
            if value is None:
                return False
            
            # Empty string = fail-secure
            if isinstance(value, str) and not value.strip():
                return False
        
        # Special validation for ttl_seconds: must be integer in [1, 3600]
        ttl = request.get("ttl_seconds")
        if not isinstance(ttl, int) or ttl < 1 or ttl > 3600:
            return False
        
        # All Keyman conditions satisfied
        return True
    
    def get_missing_keyman_conditions(self, request: Dict[str, Any]) -> List[str]:
        """
        Identify which Keyman conditions are missing (for audit/diagnostics).
        
        Args:
            request (dict): Keyman authorization request.
        
        Returns:
            list[str]: List of missing/invalid condition names. Empty list if all satisfied.
        
        Example:
            >>> engine = GovernancePolicyEngine()
            >>> request = {"trace_id": "req-001", "ttl_seconds": 7200}
            >>> engine.get_missing_keyman_conditions(request)
            ['scope', 'ttl_seconds (out of range)']
        """
        missing = []
        
        if not isinstance(request, dict):
            return list(self.REQUIRED_KEYMAN_FIELDS)
        
        # Check each mandatory field
        for field in self.REQUIRED_KEYMAN_FIELDS:
            value = request.get(field)
            
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field)
        
        # Special check for ttl_seconds range
        ttl = request.get("ttl_seconds")
        if ttl is not None:
            if not isinstance(ttl, int) or ttl < 1 or ttl > 3600:
                missing.append("ttl_seconds (out of range: must be [1, 3600])")
        
        return missing
    
    # ==================== POLICY DOCUMENTATION ====================
    
    def describe_policy(self) -> Dict[str, Any]:
        """
        Return a human-readable description of the governance policy.
        
        Useful for logging, debugging, and auditing the active policy configuration.
        
        Returns:
            dict: Policy summary including thresholds, required fields, and actions.
        
        Example:
            >>> engine = GovernancePolicyEngine()
            >>> policy = engine.describe_policy()
            >>> print(policy["neo_thresholds"])
        """
        return {
            "constitution": "v0.3",
            "neo_thresholds": {
                "allow": f"risk < {self.RISK_THRESHOLD_WARN}",
                "warn": f"{self.RISK_THRESHOLD_WARN} <= risk < {self.RISK_THRESHOLD_DENY}",
                "deny": f"{self.RISK_THRESHOLD_DENY} <= risk < {self.RISK_THRESHOLD_FUSE}",
                "fuse": f"{self.RISK_THRESHOLD_FUSE} <= risk < {self.RISK_THRESHOLD_KILL}",
                "kill": f"risk >= {self.RISK_THRESHOLD_KILL}",
            },
            "execution_preconditions": list(self.REQUIRED_EXECUTION_FIELDS),
            "keyman_conditions": list(self.REQUIRED_KEYMAN_FIELDS),
            "keyman_ttl_range": f"[{1}, {3600}]",
        }
