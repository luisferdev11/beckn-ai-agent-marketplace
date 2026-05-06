
import json
import os
import urllib.request
import urllib.error

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"   # cheapest + fastest on Groq free tier
MAX_TOKENS   = 400                       # keeps responses short and within free limits


def call_llm(prompt: str, system: str = "") -> tuple[str, int]:
    """
    Send a prompt to the LLM and return (response_text, total_tokens_used).

    Args:
        prompt: the user message
        system: optional system instruction (sets the LLM's role/behaviour)

    Returns:
        (text, token_count) — text is the LLM answer,
        token_count is the exact number reported by the API
    """
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set.\n"
            "In PowerShell run:  $env:GROQ_API_KEY='gsk_your-key-here'\n"
            "Get a free key at:  console.groq.com"
        )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = json.dumps({
        "model":       GROQ_MODEL,
        "messages":    messages,
        "max_tokens":  MAX_TOKENS,
        "temperature": 0.2,
    }).encode()

    req = urllib.request.Request(
        GROQ_URL,
        data=body,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            # Groq sits behind Cloudflare; the default Python-urllib UA is
            # blocked with a 1010 error. Set a normal-looking UA.
            "User-Agent":    "Mozilla/5.0 (compatible; beckn-ai-marketplace/agents-serg)",
            "Accept":        "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data   = json.loads(resp.read())
            text   = data["choices"][0]["message"]["content"].strip()
            tokens = data["usage"]["total_tokens"]
            return text, tokens

    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Groq API error {e.code}: {e.read().decode()}")

    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Groq API: {e}")
