import random
import re
import logging
import time

_bad_topic_patterns = [
    # reuse some basic blacklist if needed (optional)
    re.compile(r"^\s*do not\b", re.IGNORECASE),
    re.compile(r"instructions?", re.IGNORECASE),
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

def pick_topic(config, llm_pipeline=None):
    topics_cfg = config.get("topics", {})
    use_llm = topics_cfg.get("use_llm_for_topic", False)

    if use_llm and llm_pipeline:
        # LLM-based topic (you can reuse earlier improved picker logic if desired)
        seed = topics_cfg.get(
            "llm_topic_seed",
            "Give me a concise, interesting topic to explore in a stream of consciousness style. Respond with just the topic phrase only."
        )
        prompt = f"{seed}\n\nRespond with a concise topic phrase only."
        raw = llm_pipeline.generate(prompt)
        topic = sanitize_topic(raw)
        if topic:
            # optional: reject clearly bad outputs
            for pat in _bad_topic_patterns:
                if pat.search(topic):
                    logging.getLogger("streamer").warning(f"LLM returned undesirable topic '{topic}', falling back.")
                    return pick_static_topic(config)
            return topic
        logging.getLogger("streamer").warning("LLM topic generation empty; falling back to static.")
        return pick_static_topic(config)
    else:
        return pick_static_topic(config)

def pick_static_topic(config):
    static = config.get("topics", {}).get("static", [])
    if not static or not isinstance(static, list):
        raise ValueError("No static topics defined in config['topics']['static'].")
    return random.choice(static)
