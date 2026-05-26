from enum import Enum


class OrchestratorState(str, Enum):
    UNDERSTAND_TASK = "UNDERSTAND_TASK"
    DEFINE_PROMPT = "DEFINE_PROMPT"
    EXECUTE_AGENT = "EXECUTE_AGENT"
    VALIDATE_RESPONSE = "VALIDATE_RESPONSE"
    DELIVER_RESULT = "DELIVER_RESULT"


VALID_TRANSITIONS: dict[OrchestratorState, set[OrchestratorState]] = {
    OrchestratorState.UNDERSTAND_TASK: {OrchestratorState.DEFINE_PROMPT, OrchestratorState.DELIVER_RESULT},
    OrchestratorState.DEFINE_PROMPT: {OrchestratorState.EXECUTE_AGENT},
    OrchestratorState.EXECUTE_AGENT: {OrchestratorState.VALIDATE_RESPONSE},
    OrchestratorState.VALIDATE_RESPONSE: {
        OrchestratorState.DEFINE_PROMPT,    # retry with fix_instructions
        OrchestratorState.EXECUTE_AGENT,    # retry agent call
        OrchestratorState.DELIVER_RESULT,   # last step done
    },
    OrchestratorState.DELIVER_RESULT: set(),
}


def can_transition(current: OrchestratorState, target: OrchestratorState) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())
