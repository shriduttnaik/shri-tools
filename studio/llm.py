"""Story AI providers. Ollama (on this laptop, the default) is in writer.py; this module talks to the cloud options:

  claude   Anthropic Claude (official anthropic SDK; JSON guaranteed by output_config json_schema)
  openai   ChatGPT / OpenAI (Chat Completions with a strict json_schema response format)
  gemini   Google Gemini (generateContent with a JSON response)
  compat   any OpenAI-compatible service: OpenRouter, Groq, DeepSeek, Together, LM Studio ... (base URL + key)

Every call returns the parsed JSON object. Cloud providers send the story prompts (idea, characters, lines) to that
company and cost money per use; keys stay in library/settings.json on this laptop.
"""
import copy, json, re, urllib.error, urllib.request

DEFAULT_MODELS = {"claude": "claude-opus-5-5", "openai": "gpt-5-mini", "gemini": "gemini-2.5-flash", "compat": ""}


def strict(schema):
    """Structured outputs need additionalProperties: false on every object and every property listed as required."""
    s = copy.deepcopy(schema)

    def walk(x):
        if isinstance(x, dict):
            if x.get("type") == "object":
                x["additionalProperties"] = False
                if "properties" in x:
                    x["required"] = list(x["properties"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(s)
    return s


def split(messages):
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    rest = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    return system, rest


def parse(text):
    m = re.search(r"\{[\s\S]*\}", text or "")
    return json.loads(m.group(0) if m else text)


def http_json(url, body, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                               **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{url.split('/')[2]} said {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")


# ---------- Claude (Anthropic) ----------
def ask_claude(messages, schema, st, timeout):
    import anthropic
    key = (st.get("anthropic_api_key") or "").strip()
    client = anthropic.Anthropic(api_key=key, timeout=timeout) if key else anthropic.Anthropic(timeout=timeout)
    system, rest = split(messages)
    model = (st.get("llm_model") or "").strip() or DEFAULT_MODELS["claude"]
    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=system or anthropic.NOT_GIVEN,
            messages=rest,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": strict(schema)}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # if this model declines on policy grounds, the API retries on a suitable model
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("Claude: the API key was not accepted - check it in Settings")
    except anthropic.NotFoundError:
        raise RuntimeError(f"Claude: model '{model}' not found - check the model name in Settings")
    except anthropic.RateLimitError:
        raise RuntimeError("Claude: rate limit reached - try again in a minute")
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude: {e.status_code} {e.message}")
    except anthropic.APIConnectionError:
        raise RuntimeError("Claude: no connection - check the internet")
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request - change the idea a little or use another story AI")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off - ask for fewer scenes")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(text)


# ---------- ChatGPT / OpenAI and OpenAI-compatible ----------
def ask_openai(messages, schema, st, timeout, compat=False):
    if compat:
        base = (st.get("compat_base_url") or "").rstrip("/")
        key = (st.get("compat_api_key") or "").strip()
        if not base:
            raise RuntimeError("set the base URL of the OpenAI-compatible service in Settings")
    else:
        base, key = "https://api.openai.com/v1", (st.get("openai_api_key") or "").strip()
        if not key:
            raise RuntimeError("add your OpenAI API key in Settings")
    model = (st.get("llm_model") or "").strip() or DEFAULT_MODELS["compat" if compat else "openai"]
    if not model:
        raise RuntimeError("set the model name in Settings")
    body = {"model": model, "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": strict(schema),
                                                                         "strict": True}}}
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        out = http_json(base + "/chat/completions", body, headers, timeout)
    except RuntimeError as e:
        if compat and ("response_format" in str(e) or "json_schema" in str(e)):  # older servers: plain JSON mode
            body["response_format"] = {"type": "json_object"}
            body["messages"] = messages + [{"role": "user", "content": "Answer with JSON only, matching this schema: "
                                                                        + json.dumps(schema)}]
            out = http_json(base + "/chat/completions", body, headers, timeout)
        else:
            raise
    return parse(out["choices"][0]["message"].get("content") or "")


# ---------- Gemini ----------
def ask_gemini(messages, schema, st, timeout):
    key = (st.get("gemini_api_key") or "").strip()
    if not key:
        raise RuntimeError("add your Gemini API key in Settings")
    model = (st.get("llm_model") or "").strip() or DEFAULT_MODELS["gemini"]
    system, rest = split(messages)
    body = {"contents": [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
                         for m in rest],
            "generationConfig": {"responseMimeType": "application/json"}}
    sysmsg = (system + "\n\n" if system else "") + "Answer with JSON only, matching this JSON schema: " + json.dumps(schema)
    body["systemInstruction"] = {"parts": [{"text": sysmsg}]}
    out = http_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", body,
                    {"x-goog-api-key": key}, timeout)
    cands = out.get("candidates") or []
    if not cands:
        raise RuntimeError("Gemini gave no answer: " + json.dumps(out.get("promptFeedback", {}))[:300])
    return parse("".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])))


def ask(provider, messages, schema, st, timeout=900):
    if provider == "claude":
        return ask_claude(messages, schema, st, timeout)
    if provider == "openai":
        return ask_openai(messages, schema, st, timeout)
    if provider == "compat":
        return ask_openai(messages, schema, st, timeout, compat=True)
    if provider == "gemini":
        return ask_gemini(messages, schema, st, timeout)
    raise RuntimeError(f"unknown story AI provider '{provider}'")
