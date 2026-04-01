import unittest
from supervisor.plugins.neo_guardian.mcp_interceptor import MCPInterceptor, ToolManifest, GovernanceDecision

class TestMCPGovernance(unittest.TestCase):
    def setUp(self):
        # Simulamos um manifesto de ferramenta BASH governável
        bash_manifest = ToolManifest(
            name="bash",
            description="Run commands",
            requires_approval=True,
            input_schema={"properties": {"command": {"type": "string"}}},
            forbidden_values=["/etc/shadow", "rm -rf /"]
        )
        self.interceptor = MCPInterceptor({"bash": bash_manifest})

    def test_claude_leak_bypass_blocked(self):
        # O agente tenta usar o parâmetro perigoso do código vazado
        dangerous_args = {
            "command": "ls",
            "dangerouslyDisableSandbox": True
        }
        decision, reason = self.interceptor.inspect_call("bash", dangerous_args)
        
        self.assertEqual(decision, GovernanceDecision.REJECT)
        self.assertIn("disable sandbox", reason)
        print(f"PASSED: Dangerous parameter blocked. Reason: {reason}")

    def test_unauthorized_parameter_blocked(self):
        # Tentativa de injetar campos estranhos ao manifesto
        args = {
            "command": "ls",
            "hidden_flag": "true"
        }
        decision, reason = self.interceptor.inspect_call("bash", args)
        self.assertEqual(decision, GovernanceDecision.REJECT)
        self.assertIn("Unauthorized parameter injection", reason)
        print(f"PASSED: Payload noise injection blocked. Reason: {reason}")

    def test_requires_approval(self):
        # Comando legítimo cai na Regra 0
        args = {"command": "ls"}
        decision, reason = self.interceptor.inspect_call("bash", args)
        self.assertEqual(decision, GovernanceDecision.PENDING_APPROVAL)
        print(f"PASSED: Rule 0 enforced. Reason: {reason}")

    def test_forbidden_pattern(self):
        # Tentativa de violar chokepoint de arquivo do sistema
        args = {"command": "cat /etc/shadow"}
        decision, reason = self.interceptor.inspect_call("bash", args)
        self.assertEqual(decision, GovernanceDecision.REJECT)
        self.assertIn("Forbidden pattern detected", reason)
        print(f"PASSED: Threat signature blocked. Reason: {reason}")

if __name__ == "__main__":
    unittest.main()
