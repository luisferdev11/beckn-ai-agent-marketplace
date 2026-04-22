import os

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

if not os.environ.get("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY environment variable is not set")

MODEL_NAME = "llama-3.3-70b-versatile"

_metrics = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
}

_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are an expert code reviewer. Analyze the provided code and give "
            "structured feedback covering: 1) Code quality & readability, "
            "2) Potential bugs or logic errors, 3) Security issues, "
            "4) Performance improvements, 5) Best practices & suggestions."
        ),
    ),
    (
        "human",
        "Review the following {language} code:\n\n"
        "```{language}\n{code}\n```\n\n"
        "Additional context: {context}",
    ),
])


def _get_llm() -> ChatGroq:
    return ChatGroq(
        api_key=os.environ.get("GROQ_API_KEY"),
        model_name=MODEL_NAME,
        temperature=0.3,
    )


async def run_task(payload: dict) -> tuple:
    """Run a code review task. Returns (result, usage)."""
    _metrics["total_requests"] += 1

    code = payload.get("code", "")
    language = payload.get("language", "unknown")
    context = payload.get("context") or "No additional context provided."

    chain = _prompt | _get_llm()

    try:
        response = await chain.ainvoke({"language": language, "code": code, "context": context})
    except Exception:
        _metrics["failed_requests"] += 1
        raise

    usage_meta = getattr(response, "usage_metadata", {}) or {}
    input_tokens = usage_meta.get("input_tokens", 0)
    output_tokens = usage_meta.get("output_tokens", 0)

    _metrics["successful_requests"] += 1
    _metrics["total_input_tokens"] += input_tokens
    _metrics["total_output_tokens"] += output_tokens

    result = {"review": response.content, "language": language}
    usage = {
        "model_used": MODEL_NAME,
        "fallback_used": False,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    return result, usage


async def check_model() -> bool:
    try:
        llm = _get_llm()
        response = await llm.ainvoke([HumanMessage(content="ping")])
        return bool(response.content)
    except Exception:
        return False


def get_metrics() -> dict:
    return {
        "agent_id": "agent-code-reviewer-001",
        "total_requests": _metrics["total_requests"],
        "successful_requests": _metrics["successful_requests"],
        "failed_requests": _metrics["failed_requests"],
        "total_input_tokens": _metrics["total_input_tokens"],
        "total_output_tokens": _metrics["total_output_tokens"],
    }
