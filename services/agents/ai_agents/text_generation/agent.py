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
        "You are a helpful, knowledgeable AI assistant. Answer the user's question "
        "clearly and thoroughly. Respond in the same language the user writes in.",
    ),
    ("human", "{prompt}"),
])


def _get_llm() -> ChatGroq:
    return ChatGroq(
        api_key=os.environ.get("GROQ_API_KEY"),
        model_name=MODEL_NAME,
        temperature=0.7,
    )


async def run_task(payload: dict) -> tuple:
    """Run a text generation task. Returns (result, usage)."""
    _metrics["total_requests"] += 1

    prompt = payload.get("prompt", payload.get("text", payload.get("code", "")))
    if not prompt:
        _metrics["failed_requests"] += 1
        raise ValueError("No prompt provided. Send {\"prompt\": \"your question\"}")

    chain = _prompt | _get_llm()

    try:
        response = await chain.ainvoke({"prompt": prompt})
    except Exception:
        _metrics["failed_requests"] += 1
        raise

    usage_meta = getattr(response, "usage_metadata", {}) or {}
    input_tokens = usage_meta.get("input_tokens", 0)
    output_tokens = usage_meta.get("output_tokens", 0)

    _metrics["successful_requests"] += 1
    _metrics["total_input_tokens"] += input_tokens
    _metrics["total_output_tokens"] += output_tokens

    result = {"text": response.content}
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
        "agent_id": "text-generator",
        "total_requests": _metrics["total_requests"],
        "successful_requests": _metrics["successful_requests"],
        "failed_requests": _metrics["failed_requests"],
        "total_input_tokens": _metrics["total_input_tokens"],
        "total_output_tokens": _metrics["total_output_tokens"],
    }
