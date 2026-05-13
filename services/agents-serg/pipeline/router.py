"""
Pipeline Router — executes a sequence of agents where each step's
output becomes the next step's input.

Example pipeline request:
  steps: [
    { "agent_id": "extractor-v1",  "task_type": "extract",   "payload": {"text": "...", "extract": "names"} },
    { "agent_id": "translator-v1", "task_type": "translate",  "payload": {} }
    # ↑ payload can be empty — the previous step's result is injected as "text"
  ]
"""

import time
from dataclasses import dataclass


@dataclass
class StepResult:
    step:        int
    agent_id:    str
    task_type:   str
    status:      str
    result:      str | None
    latency_ms:  float
    token_count: int
    error:       str | None = None


def run_pipeline(steps: list[dict], registry: dict) -> dict:
    """
    Execute a list of agent steps in sequence.

    Each step is a dict with:
      - agent_id  (required)
      - task_type (required)
      - payload   (optional dict — if "text" is missing, previous result is used)

    Returns a summary with each step's result and the final output.
    """
    if not steps:
        raise ValueError("Pipeline must have at least one step")

    step_results: list[StepResult] = []
    previous_output: str | None = None
    total_tokens = 0
    pipeline_start = time.perf_counter()

    for i, step in enumerate(steps):
        agent_id  = step.get("agent_id", "")
        task_type = step.get("task_type", "")
        payload   = dict(step.get("payload", {}))   # copy so we don't mutate the original

        # Validate step
        if agent_id not in registry:
            return _error_response(
                step_results, i, agent_id, task_type,
                f"Agent '{agent_id}' not found in registry",
                pipeline_start,
            )
        if task_type not in registry[agent_id]:
            return _error_response(
                step_results, i, agent_id, task_type,
                f"Task '{task_type}' not supported by '{agent_id}'",
                pipeline_start,
            )

        # Inject previous step's output as "text" if payload has no "text" key
        if previous_output and "text" not in payload:
            payload["text"] = previous_output

        agent      = registry[agent_id][task_type]
        step_start = time.perf_counter()

        try:
            result, tokens = agent.run(payload)
            status = "success"
            error  = None
        except Exception as e:
            result = None
            tokens = 0
            status = "failure"
            error  = str(e)

        elapsed = (time.perf_counter() - step_start) * 1000
        total_tokens += tokens

        step_result = StepResult(
            step        = i + 1,
            agent_id    = agent_id,
            task_type   = task_type,
            status      = status,
            result      = result,
            latency_ms  = round(elapsed, 2),
            token_count = tokens,
            error       = error,
        )
        step_results.append(step_result)

        if status == "failure":
            # Stop the pipeline on first failure
            break

        previous_output = result

    total_elapsed = round((time.perf_counter() - pipeline_start) * 1000, 2)
    all_passed    = all(s.status == "success" for s in step_results)

    return {
        "status":            "success" if all_passed else "failure",
        "total_steps":       len(steps),
        "completed_steps":   len(step_results),
        "total_latency_ms":  total_elapsed,
        "total_token_count": total_tokens,
        "final_output":      step_results[-1].result if step_results else None,
        "steps": [
            {
                "step":        r.step,
                "agent_id":    r.agent_id,
                "task_type":   r.task_type,
                "status":      r.status,
                "result":      r.result,
                "latency_ms":  r.latency_ms,
                "token_count": r.token_count,
                "error":       r.error,
            }
            for r in step_results
        ],
    }


def _error_response(step_results, step_index, agent_id, task_type,
                    message, pipeline_start):
    total_elapsed = round((time.perf_counter() - pipeline_start) * 1000, 2)
    return {
        "status":            "failure",
        "total_steps":       step_index + 1,
        "completed_steps":   len(step_results),
        "total_latency_ms":  total_elapsed,
        "total_token_count": sum(s.token_count for s in step_results),
        "final_output":      None,
        "error":             message,
        "steps": [
            {
                "step":        r.step,
                "agent_id":    r.agent_id,
                "task_type":   r.task_type,
                "status":      r.status,
                "result":      r.result,
                "latency_ms":  r.latency_ms,
                "token_count": r.token_count,
                "error":       r.error,
            }
            for r in step_results
        ],
    }
