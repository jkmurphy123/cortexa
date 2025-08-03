import re
import logging
import time

def sanitize_topic(raw: str) -> str:
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    line = lines[0]
    line = re.sub(r'^["\']+|["\']+$', '', line).strip()
    if len(line) > 100:
        line = line[:100].rsplit(" ", 1)[0]
    return line

def pick_topic_via_llm(config, llm_pipeline, retries: int = 2, wait_between: float = 0.5):
    """
    Uses the LLM to generate a concise topic. Retries if output is empty or looks invalid.
    """
    seed_base = config.get("topics", {}).get(
        "llm_topic_seed",
        "Give me an evocative, concise topic to explore in a stream of consciousness style. Respond with just the topic phrase."
    )

    # Add a couple of few-shot examples to anchor format
    prompt = (
        f"{seed_base}\n\n"
        "Examples:\n"
        "- forgotten childhood smells\n"
        "- late-night urban markets\n"
        "- the sound of rain on tin roofs\n\n"
        "Respond with just one topic phrase, 2–4 words, no explanation."
    )

    for attempt in range(1, retries + 2):
        raw = llm_pipeline.generate(prompt)
        topic = sanitize_topic(raw)
        logging.getLogger("streamer").debug(f"[topic_picker] attempt {attempt}, raw topic output: {raw!r}, sanitized: {topic!r}")
        if topic:
            return topic
        if attempt <= retries:
            time.sleep(wait_between)
    # fallback
    logging.getLogger("streamer").warning("Topic generation failed; falling back to default topic.")
    return "the meaning of revenge"
