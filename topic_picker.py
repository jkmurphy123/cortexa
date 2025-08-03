import re

def sanitize_topic(raw: str) -> str:
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    line = lines[0]
    line = re.sub(r'^["\']+|["\']+$', '', line).strip()
    if len(line) > 100:
        line = line[:100].rsplit(" ", 1)[0]
    return line

def pick_topic_via_llm(config, llm_pipeline):
    """
    Uses the LLM to generate a topic based on the seed prompt.
    Falls back to a default if generation fails.
    """
    seed = config.get("topics", {}).get(
        "llm_topic_seed",
        "Give me a concise, interesting topic to explore in a stream of consciousness style. Respond with just the topic phrase."
    )
    prompt = f"{seed}\n\nRespond with a concise topic phrase only."
    raw = llm_pipeline.generate(prompt)
    topic = sanitize_topic(raw)
    if not topic:
        return "the meaning of nostalgia"
    return topic
