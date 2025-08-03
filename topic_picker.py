import re

def pick_topic_via_llm(config, llm_pipeline):
    """
    Always uses the LLM to generate a topic based on the seed prompt.
    Falls back to a safe default if generation fails or is empty.
    """
    seed = config.get("topics", {}).get(
        "llm_topic_seed",
        "Give me a random topic to explore in a stream of consciousness style. Respond with just the topic phrase."
    )
    prompt = f"{seed}\n\nRespond with a concise topic phrase only."
    raw = llm_pipeline.generate(prompt)
    topic = sanitize_topic(raw)
    if not topic:
        # fallback
        return "the meaning of nostalgia"
    return topic

def sanitize_topic(raw: str) -> str:
    # Take first line, strip extraneous punctuation/spaces
    line = raw.strip().splitlines()[0]
    # Remove surrounding quotes if present
    line = re.sub(r'^["\']+|["\']+$', '', line).strip()
    # Optionally truncate to reasonable length
    if len(line) > 100:
        line = line[:100].rsplit(" ", 1)[0]
    return line
