from typing import Dict, Any, List, Tuple
from enum import Enum
from dataclasses import dataclass, field

class GovernanceDecision(Enum):
    ALLOW = "ALLOW"
    REJECT = "REJECT"
    PENDING_APPROVAL = "PENDING_APPROVAL" # REGRA 0

@dataclass
class ToolManifest:
    name: str
    description: str
    requires_approval: bool = True
    max_tokens_per_call: int = 4096
    timeout_seconds: int = 30
    input_schema: Dict[str, Any] = field(default_factory=dict)
    forbidden_values: List[str] = field(default_factory=list)

class MCPInterceptor:
    """
    Interceptor de Orquestração MCP (Clean Room Design).
    Baseado na arquitetura de Harness identificada no claw-code, 
    mas operando como Enforcement Boundary implacável do UnifAI.
    """
    def __init__(self, registry: Dict[str, ToolManifest] = None):
         self.registry = registry or {}

    def register_tool(self, manifest: ToolManifest):
         self.registry[manifest.name] = manifest

    def inspect_call(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[GovernanceDecision, str]:
        # 1. Discovery (Isolamento de Manifestos)
        manifest = self.registry.get(tool_name)
        if not manifest:
            return GovernanceDecision.REJECT, f"Tool '{tool_name}' not in Governance Manifest."

        # 2. Governance-bypass attempt detection.
        # dangerouslyDisableSandbox is the real parameter Claude Code sends; block it as primary.
        # dangerouslyBypassGovernance is an internal alias; block it too.
        if arguments.get("dangerouslyDisableSandbox") is True or arguments.get("dangerouslyBypassGovernance") is True:
            return GovernanceDecision.REJECT, "CRITICAL: Agent attempted to bypass governance. Triggering Oracle incident."

        # 3. Parameter Validation (Strictness)
        # Verificamos se o agente está injetando parâmetros não autorizados
        allowed_keys = manifest.input_schema.get("properties", {}).keys()
        for key in arguments.keys():
            if key not in allowed_keys:
                return GovernanceDecision.REJECT, f"Unauthorized parameter injection: {key}"

        # 4. Pattern & Path Checking (Baseado no 02_PROMPTS_GUARDRAILS)
        # Varre argumentos em busca de padrões proibidos (ex: caminhos de sistema)
        arg_string = str(arguments).lower()
        for pattern in manifest.forbidden_values:
            if pattern.lower() in arg_string:
                return GovernanceDecision.REJECT, f"Forbidden pattern detected in arguments: {pattern}"

        # 5. Resource & Execution Limits
        requested_timeout = arguments.get("timeout")
        if requested_timeout and isinstance(requested_timeout, (int, float)):
            if requested_timeout > manifest.timeout_seconds:
                return GovernanceDecision.REJECT, f"Requested timeout ({requested_timeout}s) strictly exceeds manifest limit ({manifest.timeout_seconds}s). Agent attempting resource exhaustion."

        if arguments.get("run_in_background") is True:
            return GovernanceDecision.PENDING_APPROVAL, "CRITICAL: Agent requested background execution. Possible silent data exfiltration vector. Rerouting to Rule 0 (Human)."

        # 6. Rule 0 Enforcement
        if manifest.requires_approval:
            return GovernanceDecision.PENDING_APPROVAL, f"Tool '{tool_name}' requires Human-in-the-loop authorization."

        # TODO: Sincronização com o Bill. 
        # O Neo deve reportar o "estimated_token_cost" extraído via max_tokens_per_call para o plugin Bill antes da liberação da tarefa final.
        return GovernanceDecision.ALLOW, "Pre-execution checks passed."
