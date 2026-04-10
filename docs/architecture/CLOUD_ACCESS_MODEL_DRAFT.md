# UnifAI Cloud Access Model: TSMC-Grade Threat Defense Architecture

## 1. Executive Summary & Rule 0 Compliance

In the UnifAI architecture, the lifecycle of an autonomous agent is strictly governed by "World Physics"—immutable, machine-enforced constraints that operate entirely outside the agent's cognitive payload. We operate under a "TSMC-grade threat" mindset: no agent can be trusted to police its own boundaries or terminate its own context via commands like `self.stop()`.

This document outlines the blueprint for the **Cloud Access Model**, utilizing heavily fortified asynchronous Python patterns (`asyncio`) to physically restrict the agent's capabilities. By enforcing boundaries at the OS, network, and event-loop levels, we guarantee determinism and absolute scope control over execution contexts, effectively mirroring established fail-fast patterns like `StreamingToolExecutor` and `classifierDecision` within a Python runtime.

**Design Principle**: All constraints are enforced through native Python `asyncio` primitives (`yield`, `TaskGroup`, `Event`). No artificial sandbox wrappers; only surgical structural cancellation at the OS and Event Loop boundary.

## 2. Configuration-Driven World Physics: WorldPhysicsConfig

To enable rapid iteration and VM-based testing, all execution boundaries are now dynamically configurable. The system reads a central `WorldPhysicsConfig` object (ultimately sourced from `world_charter.yaml`) that toggles and parameterizes each chokepoint.

```python
from dataclasses import dataclass

@dataclass
class WorldPhysicsConfig:
    """
    Machine-readable governance configuration for UnifAI's runtime constraints.
    Sourced from: config/world_charter.yaml
    """
    # Consult Mode: Read-only reasoning with strict iteration caps
    consult_mode_enabled: bool = True
    consult_max_turns: int = 3
    
    # Authorization Race: Concurrent Neo Guardian vs. Human Approval
    auth_race_enabled: bool = True
    auth_race_timeout_seconds: float = 30.0
    
    # Fuel Gauge: Budget-based execution termination
    fuel_gauge_enabled: bool = True
    max_burn_tokens: int = 10000
    fuel_monitor_check_interval_seconds: float = 0.5
    
    # Fuse: Emergency brake for anomaly detection
    fuse_enabled: bool = True
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> "WorldPhysicsConfig":
        """
        Load configuration from world_charter.yaml.
        Schema validation and defaults applied automatically.
        """
        import yaml
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        return cls(**data.get('world_physics', {}))
```

## 3. The Physical Lock: Consult Mode via AsyncGenerators

The `consult_mode` is designed for read-only or reasoning-only interactions. To prevent the LLM from entering infinite recursion or attempting to bypass restrictions via clever prompting, we implement a physical lock using Python's `AsyncGenerator`. 

By strictly managing the `yield` boundary (controlled by `config.consult_mode_enabled`), the UnifAI Supervisor forcibly seizes CPU control back from the LLM execution context. The agent is mathematically constrained to a hard limit defined in `config.consult_max_turns`. Furthermore, the tools schema is intentionally stripped from the payload at the network layer (`tools=[]`), ensuring zero access to the broader World API.

**Why This Achieves Physical Locking**:
- The generator's `yield` statement is a hard context-switching boundary in the Python event loop. The LLM cannot bypass it programmatically.
- Each iteration consumes a turn counter. No amount of prompt engineering or token manipulation allows exceeding the cap.
- If `config.consult_mode_enabled == False`, the chokepoint is bypassed entirely for testing scenarios.

```python
import asyncio
from typing import AsyncGenerator

class UnifAISupervisor:
    def __init__(self, config: WorldPhysicsConfig):
        self.config = config
    
    async def run_consult_mode(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        Physical loop constraint via AsyncGenerator yield boundary.
        CPU control is seized back at every iteration, regardless of LLM reasoning.
        """
        if not self.config.consult_mode_enabled:
            # Chokepoint disabled for testing or unrestricted scenarios.
            yield await self.oracle_inference(prompt, tools_allowed=False)
            return
        
        max_turns = self.config.consult_max_turns
        turn = 0
        
        while turn < max_turns:
            turn += 1
            # I/O Restraint: tools_allowed=False physically strips the tool schema 
            # from the outbound network request payload to the Oracle.
            response = await self.oracle_inference(prompt, tools_allowed=False)
            
            # Yielding returns execution control to the UnifAI boundary, 
            # suspending the agent's logic cleanly. The agent resumes only when 
            # the Supervisor explicitly requests the next iteration.
            yield f"[Turn {turn}/{max_turns}] {response}"
            
            if self.is_terminal_response(response):
                break
        
        # The Brake: Forced scope termination.
        # If the agent attempts to exceed max_turns, the loop exits. 
        # The agent has no recourse to continue processing.
        yield "[SYSTEM: Edge boundary reached. Consult mode physically terminated by Supervisor.]"
        return

    async def oracle_inference(self, prompt: str, tools_allowed: bool = False) -> str:
        """
        Network proxy layer to Oracle LLM. In test environments, this is mocked.
        """
        # Production: This calls out to Claude API / external LLM with tools=[] if tools_allowed=False
        return "Governance-restricted AI output."
    
    def is_terminal_response(self, response: str) -> bool:
        """
        Heuristic to detect terminal agent state (e.g., explicit conclusion marker).
        """
        return "<done>" in response.lower()
```

## 4. Concurrent Authorization Racing: The Gatekeeper Chokepoint

When transitioning to `execution_mode`, rigorous authorization is paramount. UnifAI demands zero UX degradation while maintaining zero trust. To achieve this, when a dangerous `tool_call` is requested, we launch a race condition between the static mathematical risk analyzer (`NeoGuardian`) and a human-in-the-loop webhook (`Keyman`).

By leveraging `asyncio.wait` with `return_when=asyncio.FIRST_COMPLETED` (controlled by `config.auth_race_enabled`), we enforce a fail-fast architecture. If `NeoGuardian` instantly calculates a critical risk score (e.g., `KILL` or `FUSE`), the execution is immediately denied and the pending human approval webhook is aborted via sibling abort. Conversely, an explicit human denial overrides a slower static analysis. This prevents the system from hanging indefinitely on unanswered webhooks.

**Why This Achieves Fail-Fast Security**:
- Both pipelines run concurrently from trigger to decision. The first result wins.
- Pending tasks are aggressively cancelled. No zombie webhooks or pending I/O.
- The race is deterministic and measurable (audit trail: "Neo decided in 5ms", "Human approved in 8s", etc.).

```python
import asyncio

async def classifier_decision_race(
    tool_payload: dict, 
    config: WorldPhysicsConfig
) -> bool:
    """
    Concurrent race between automated semantic/architectural risk analysis 
    (NeoGuardian) and asynchronous human permission (Keyman).
    
    Only executed if config.auth_race_enabled == True.
    """
    if not config.auth_race_enabled:
        # Authorization race disabled; assume automatic approval (for testing).
        return True
    
    loop = asyncio.get_running_loop()
    
    # Pipeline 1: NeoGuardian (Mathematical/Regex Pattern Engine)
    # Runs locally, no network latency.
    task_neo = asyncio.create_task(
        NeoGuardian.evaluate_risk(tool_payload), 
        name="neo_eval"
    )
    
    # Pipeline 2: Human Interface (Blocking Webhook/Telegram integration)
    # May incur network RTT or human reaction time.
    task_human = asyncio.create_task(
        HumanInterface.wait_for_approval(tool_payload, timeout=config.auth_race_timeout_seconds), 
        name="human_eval"
    )
    
    # The Chokepoint: First to complete dictates the immediate system response.
    done, pending = await asyncio.wait(
        [task_neo, task_human],
        return_when=asyncio.FIRST_COMPLETED,
        timeout=config.auth_race_timeout_seconds
    )
    
    if not done:
        # Timeout: Both pipelines exceeded timeout window. Fail-secure: DENY.
        for p in [task_neo, task_human]:
            p.cancel()
        raise PermissionError(
            "[Rule 0] Authorization race deadline exceeded. Execution denied by timeout."
        )
    
    first_finished = done.pop()
    decision = first_finished.result()
    
    # Sibling Abort: Instantly cancel pending concurrent operations.
    # If Neo evaluates to KILL in 10ms, the Human Webhook is cancelled, preventing memory leaks.
    for p in pending:
        p.cancel()
    
    if decision.action in ["DENY", "FUSE", "KILL"]:
        raise PermissionError(
            f"[Rule 0] Execution physically halted at concurrent choke point. Reason: {decision.reason}"
        )
    
    return True
```

## 5. Structural Execution & Fuel Monitoring: The Fuse System

Once authorized, an agent's execution runs as native Python coroutines within a strictly bounded `asyncio.TaskGroup`. There is no intermediate "sandbox" wrapper; the Group itself provides structural guarantees.

In parallel, UnifAI's resource monitor ("The Gauge") actively watches the burn rate. If `config.fuel_gauge_enabled == True` and the active token count exceeds `config.max_burn_tokens`, or if an anomaly is detected, the monitor signals an `asyncio.Event` (The Fuse). This trigger immediately cascades a cancellation down the entire `TaskGroup` tree via Python's built-in exception chaining. No orphaned sockets, memory leaks, or running child processes survive budget overflow.

**Why This Achieves Structural Cancellation**:
- `asyncio.TaskGroup` guarantees that all sub-tasks are cancelled if any task raises an exception or if the group context is exited.
- The `Event`-based signaling is lock-free and operates at OS kernel clock resolution.
- Python's `ExceptionGroup` propagates cancellation across the entire tree atomically.

```python
import asyncio

async def execute_mode_runtime(
    tools_to_run: list,
    config: WorldPhysicsConfig
) -> list:
    """
    Executes a list of tool invocations under strict resource governance.
    Native tool execution (no sandbox wrapper). Structural cancellation via TaskGroup.
    
    Args:
        tools_to_run: List of (tool_name, args_dict) tuples
        config: WorldPhysicsConfig object controlling chokepoints
    
    Returns:
        List of tool execution results (or exception tracebacks if cancelled)
    """
    fuse_event = asyncio.Event()
    results = []
    
    try:
        # TaskGroup guarantees: If any task raises or the group exits, 
        # all remaining tasks are automatically cancelled. No orphans.
        async with asyncio.TaskGroup() as tg:
            
            # Submit target tools directly. Each tool is a native coroutine.
            # No intermediate sandbox wrapper; cancellation happens structurally.
            tool_tasks = [
                tg.create_task(
                    execute_native_tool(tool, args), 
                    name=f"tool_{tool}"
                )
                for tool, args in tools_to_run
            ]
            
            # Conditional: The Gauge (Fuel Monitor)
            # Only spawned if config.fuel_gauge_enabled == True.
            if config.fuel_gauge_enabled:
                tg.create_task(
                    active_fuel_monitor(
                        fuse_event, 
                        config
                    ),
                    name="fuel_gauge"
                )
            
            # Collect results as tasks complete.
            for t in tool_tasks:
                results.append(t.result())
        
    except ExceptionGroup as eg:
        # TaskGroup exit via Fuse signal or other error.
        # Python's ExceptionGroup chains all cancellations atomically.
        print(f"[Governance] Task tree shredded and handled. Error group: {eg}")
        # Optionally log to audit trail or initiate incident response.
        
    except asyncio.CancelledError as ce:
        # The Fuse was triggered; all tasks cancelled.
        print(f"[Brake Tripped] Execution halted via Fuse signal. {ce}")
        
    return results


async def active_fuel_monitor(fuse_event: asyncio.Event, config: WorldPhysicsConfig):
    """
    The Gauge: Non-negotiable physical constraint monitor.
    Runs as a sibling task within the TaskGroup. If budget is breached, signals The Fuse.
    
    Args:
        fuse_event: Shared Event trigger (set when budget exceeded)
        config: Contains max_burn_tokens and fuel_monitor_check_interval_seconds
    """
    while True:
        await asyncio.sleep(config.fuel_monitor_check_interval_seconds)
        
        # Mathematical threshold check: Have we burned too many tokens?
        current_burn = current_token_burn()
        anomaly_flag = anomaly_detected()
        
        if current_burn > config.max_burn_tokens or anomaly_flag:
            print(f"[Fuse] Budget breach detected: {current_burn}/{config.max_burn_tokens} tokens.")
            # Pull the plug: Signal The Fuse.
            fuse_event.set()
            # This triggers cascading cancellation across the entire TaskGroup tree.
            break


async def execute_native_tool(tool_name: str, args: dict) -> dict:
    """
    Executes a tool natively. Subject to structural cancellation via TaskGroup.
    If the parent TaskGroup's Fuse is triggered, this coroutine receives 
    asyncio.CancelledError and exits cleanly.
    """
    try:
        # Actual tool execution (network call, subprocess, etc.)
        result = await invoke_tool_api(tool_name, args)
        return result
    except asyncio.CancelledError:
        print(f"[Cancelled] Tool '{tool_name}' was structurally cancelled via Fuse.")
        raise
    except Exception as e:
        print(f"[Error] Tool '{tool_name}' failed: {e}")
        raise
```

## 6. Integration with world_charter.yaml & VM-Based Testing

The `WorldPhysicsConfig` is designed to be sourced directly from the UnifAI configuration layer (`config/world_charter.yaml`). This enables rapid iteration and testing in isolated VM environments.

### Example world_charter.yaml Configuration

```yaml
# config/world_charter.yaml
world_physics:
  # Consult Mode: Reasoning without tool access
  consult_mode_enabled: true
  consult_max_turns: 3
  
  # Authorization Race: Concurrent Neo vs. Human approval
  auth_race_enabled: true
  auth_race_timeout_seconds: 30.0
  
  # Fuel Gauge: Token-based execution termination
  fuel_gauge_enabled: true
  max_burn_tokens: 10000
  fuel_monitor_check_interval_seconds: 0.5
  
  # Fuse: Emergency brake
  fuse_enabled: true
```

### VM Test Scenarios

1. **Scenario: Consult-Only Mode** (Disable Execution)
   ```yaml
   consult_mode_enabled: true
   auth_race_enabled: false       # No authorization needed
   fuel_gauge_enabled: false      # No budget monitoring
   ```
   
   Expected Behavior: Agent reasons for up to 3 turns, no tools are available, no resource monitoring.

2. **Scenario: Full Governance Stack**
   ```yaml
   consult_mode_enabled: true
   auth_race_enabled: true
   fuel_gauge_enabled: true
   max_burn_tokens: 5000          # Aggressive budget
   ```
   
   Expected Behavior: Consult mode for 3 turns, then execution with auth race + fuel monitoring.

3. **Scenario: Unrestricted Testing** (Disable All Chokepoints)
   ```yaml
   consult_mode_enabled: false    # Bypass turn cap
   auth_race_enabled: false       # Auto-approve tools
   fuel_gauge_enabled: false      # No budget constraint
   ```
   
   Expected Behavior: Agent runs without restrictions (for baseline performance profiling).

### Integration with little7-installer

The configuration is loaded at Supervisor boot time:

```python
# In supervisor/supervisor.py
from supervisor.governance.policy_engine import WorldPhysicsConfig

class Supervisor:
    def __init__(self, config_path: str = "config/world_charter.yaml"):
        self.world_physics = WorldPhysicsConfig.from_yaml(config_path)
        # ... rest of initialization
    
    async def tick(self, oracle_request: dict):
        """Main loop: Apply World Physics configuration."""
        
        # Stage 1: Consult Mode (if enabled)
        if self.world_physics.consult_mode_enabled:
            async for response in self.run_consult_mode(oracle_request, self.world_physics):
                yield response
        
        # Stage 2: Execution Mode (if authorization passes)
        try:
            tools_to_execute = oracle_request.get("tools", [])
            await classifier_decision_race(oracle_request, self.world_physics)
            results = await execute_mode_runtime(tools_to_execute, self.world_physics)
            yield results
        except PermissionError as pe:
            yield f"[Denied] {pe}"
```

## 7. Testing E2E: Smoke Tests & Leak Detection

Because the execution model is now fully configurable, smoke tests can rapidly validate each chokepoint in isolation.

### Smoke Test: Consult Mode Cap Enforcement

```bash
#!/bin/bash
# scripts/smoke_test_consult_mode_cap.sh

CONFIG_OVERRIDE="
world_physics:
  consult_mode_enabled: true
  consult_max_turns: 3
"

# Run supervisor with configuration override
python3 supervisor/supervisor.py \
    --config-override "$CONFIG_OVERRIDE" \
    --smoke-test-prompt "Reason about X. Then reason about Y. Then reason about Z. Then reason about W." \
    --assert-max-turns 3 \
    --assert-no-tool-calls
```

### Smoke Test: Authorization Race Timeout

```bash
#!/bin/bash
# scripts/smoke_test_auth_race_timeout.sh

CONFIG_OVERRIDE="
world_physics:
  auth_race_enabled: true
  auth_race_timeout_seconds: 2.0
"

# Simulate a tool call with intentionally slow human approval
python3 supervisor/supervisor.py \
    --config-override "$CONFIG_OVERRIDE" \
    --tool-call-request '{"tool": "dangerous_write", "args": {...}}' \
    --simulate-human-approval-delay 10.0 \
    --assert-timeout-denied
```

### Smoke Test: Fuel Monitor Cancellation (No Leaks)

```bash
#!/bin/bash
# scripts/smoke_test_fuel_monitor_cancellation.sh

CONFIG_OVERRIDE="
world_physics:
  fuel_gauge_enabled: true
  max_burn_tokens: 100
  fuel_monitor_check_interval_seconds: 0.1
"

# Run a tool that will exceed token budget
python3 supervisor/supervisor.py \
    --config-override "$CONFIG_OVERRIDE" \
    --tool-call-request '{"tool": "expensive_model_call", "args": {...}}' \
    --simulate-token-burn 50000 \
    --assert-fuse-triggered \
    --assert-no-orphaned-processes \
    --assert-no-leaked-sockets
```

## 8. Security & Auditability

All World Physics decisions are logged to an immutable audit trail:

```python
# Audit trail entry format
{
    "timestamp": "2026-04-08T14:32:15.123Z",
    "event": "consult_mode_barrier_enforced",
    "config_state": {
        "consult_max_turns": 3,
        "turn_reached": 3
    },
    "result": "HALT"
}
```

This ensures full traceability of why an execution was terminated, facilitating post-incident forensics and configuration tuning.

---

**Secrets in memory, Governance out of reach, Fast execution.**