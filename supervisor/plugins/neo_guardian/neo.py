"""
Neo (System Guardian) Plugin para UnifAI Supervisor.
Este módulo aplica as Regras 0 e 4 da Constituição Lyra-Little7.
"""
import re
from typing import Dict, Any

class NeoGuardian:
    def __init__(self):
        # Heurísticas de Prompt Injection
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
        Analisa a especificação de uma tarefa em busca de ameaças.
        Retorna um dicionário recomendando a ação para o Supervisor.
        """
        report = {
            "is_safe": True,
            "recommended_action": "proceed",
            "reason": None
        }

        # Extrair texto a ser avaliado da task_spec
        # A spec do Supervisor atual tem campos como "cmd" ou "args" ou futuramente "prompt"
        content_to_check = str(task_spec.get("cmd", "")) + " " + " ".join(task_spec.get("args", []))

        # Uma tarefa mais complexa envolvendo LLM poderia ter um content ou prompt
        if "prompt" in task_spec:
             content_to_check += " " + str(task_spec["prompt"])

        # Verificar injeção de prompt
        for pattern in self.injection_patterns:
            if pattern.search(content_to_check):
                report["is_safe"] = False
                report["recommended_action"] = "trigger_kill_switch"
                report["reason"] = f"PROMPT_INJECTION_DETECTED: Padrão malicioso encontrado '{pattern.pattern}'"
                return report

        return report

