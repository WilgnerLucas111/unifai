"""
Neo (System Guardian) Plugin for UnifAI Supervisor.
This module enforces Rules 0 and 4 of the Lyra-Little7 Constitution.
"""
import re
from typing import Dict, Any

class NeoGuardian:
    def __init__(self):
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

        return report

