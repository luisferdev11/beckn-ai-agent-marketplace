
from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """
    All agents share this contract:
      - name:      unique string ID used in the registry  e.g. "summarizer-v1"
      - task_type: the task name used in /run requests    e.g. "summarize"
      - run():     receives the payload dict, returns (result_text, token_count)
    """

    name: str       # override in each subclass
    task_type: str  # override in each subclass

    @abstractmethod
    def run(self, payload: dict) -> tuple[str, int]:
        """
        Execute the agent task.

        Args:
            payload: dict sent by the caller in the POST /run body

        Returns:
            (result, token_count) — result is the text answer,
            token_count is the real number of tokens used (from the LLM response)
        """
        ...
