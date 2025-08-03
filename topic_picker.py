import re
import logging
import time

_bad_topic_patterns = [
    re.compile(r"^\s*do not\b", re.IGNORECASE),
    re.compile(r"^\s*avoid\b", re.IGNORECASE),
    re.compile(r"instructions?", re.IGNORECASE),
    re.compile(r"previous sentence", re.IGNORECASE),
    re.compile(r"paragraph", re.IGNORECASE),
]

def sanitize_topic(raw: str) -> str:
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    line = lines[0]
    line = re.sub(r'^["\']+|["\']+$', '', line).strip()
    if len(line) > 100:
        line = line[:100].rsplit(" ", 1)[0]
    return line

def is_bad_topic(candidate: str) -> bool:
    if not candidate:
        return True
    for pat in _bad_topic_patterns:
        if pat.search(candidate):
            return True
    return False

def pick_topic_via_llm(config, llm_pipeline, retries: int = 3, wait_between: float = 0.5):
    """
    Uses the LLM to generate a concise topic phrase. Filters out instruction-like junk.
    """
    seed_base = config.get("topics", {}).get(
        "llm_topic_seed",
        "Give me an evocative, concise topic to explore in a stream of consciousness style. Respond with just the topic phrase."
    )

    prompt = (
        "You are a creative topic generator. Supply exactly one concise topic phrase (2–4 words) "
        "for a stream-of-consciousness exploration. Do NOT output instructions, meta commentary, "
        "or repeat any setup text.\n\n"
        "Examples:\n"
        "- forgotten childhood smells\n"
        "- late-night urban markets\n"
        "- the sound of rain on tin roofs\n\n"
        f"{seed_base}\n"
        "Respond with exactly one topic phrase, no explanation."
    )

    for attempt in range(1, retries + 1):
        raw = llm_pipeline.generate(prompt)
        topic = sanitize_topic(raw)
        logging.getLogger("streamer").debug(
            f"[topic_picker] attempt {attempt}, raw: {raw!r}, sanitized: {topic!r}"
        )
        if not is_bad_topic(topic):
            return topic
        logging.getLogger("streamer").warning(f"Rejected bad topic '{topic}', retrying...")
        time.sleep(wait_between)

    logging.getLogger("streamer").warning("Topic generation failed cleanly; falling back to default.")
    return "the meaning of nostalgia"
