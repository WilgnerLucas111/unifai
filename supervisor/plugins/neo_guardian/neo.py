"""
Neo (System Guardian) Plugin for UnifAI Supervisor.
This module enforces Rules 0 and 4 of the Lyra-Little7 Constitution.
"""
import re
from typing import Dict, Any, Optional
from plugins.neo_guardian.mcp_interceptor import MCPInterceptor, GovernanceDecision

class NeoGuardian:
    def __init__(self, interceptor: Optional[MCPInterceptor] = None):
        self.interceptor = interceptor
        # Prompt Injection Heuristics
        self.injection_patterns = [
            re.compile(r"(?i)ignore\s*all\s*previous\s*instructions"),
            re.compile(r"(?i)forget\s*all\s*previous\s*commands"),
            re.compile(r"(?i)you\s*are\s*now\s*a\s*different\s*AI"),
            re.compile(r"(?i)system\s*prompt"),
            re.compile(r"(?i)bypassing\s*governance"),
            re.compile(r"(?i)print\s*the\s*secret"),
            re.compile(r"(?i)show\s*me\s*the\s*api\s*key")
        ]
        self.output_threat_signatures = [
            "ignore all previous",
            "ignore as instruções",
            "system prompt",
            "forget",
            "bypass",
        ]

    def sanitize_tool_output(self, tool_name: str, output: str) -> str:
        """
        Sanitizes tool output before it is returned to the model loop.
        """
        if tool_name != "read_file":
            return output

        lowered_output = output.lower()
        for signature in self.output_threat_signatures:
            if signature in lowered_output:
                return "[NEO GUARDIAN INTERVENTION: File content masked due to detected Prompt Injection signature.]"

        return output

    def analyze_task_spec(self, task_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes a task specification for threats.
        Returns a dictionary recommending the action for the Supervisor.
        """
        report = {
            "is_safe": True,
            "recommended_action": "proceed",
            "reason": None
        }

        # Extract text to be evaluated from task_spec
        # The current Supervisor spec has fields like "cmd", "args", or potentially "prompt"
        args = task_spec.get("args", [])
        if not isinstance(args, list):
            args = [args]
        
        content_parts = [str(task_spec.get("cmd", ""))]
        content_parts.extend(str(a) for a in args)
        
        # A more complex task involving LLM could have a content or prompt
        if "prompt" in task_spec:
            content_parts.append(str(task_spec["prompt"]))
            
        content_to_check = " ".join(content_parts)

        # Check for prompt injection
        for pattern in self.injection_patterns:
            if pattern.search(content_to_check):
                report["is_safe"] = False
                report["recommended_action"] = "block_task"
                report["reason"] = f"PROMPT_INJECTION_DETECTED: Malicious pattern found '{pattern.pattern}'"
                return report

        # 2. Check MCP Tool Manifest Limits (Governable Architecture)
        if self.interceptor and "tool_use" in task_spec:
            tool_intent = task_spec["tool_use"]
            tool_name = tool_intent.get("name")
            tool_args = tool_intent.get("arguments", {})

            if tool_name:
                decision, reason = self.interceptor.inspect_call(tool_name, tool_args)

                if decision == GovernanceDecision.REJECT:
                    report["is_safe"] = False
                    report["recommended_action"] = "block_task"
                    report["reason"] = f"CRITICAL_SECURITY_VIOLATION: {reason}"
                    return report

                if decision == GovernanceDecision.PENDING_APPROVAL:
                    report["is_safe"] = False
                    report["recommended_action"] = "pause_for_human"
                    report["reason"] = f"RULE_0_ENFORCEMENT: {reason}"
                    return report

        return report

