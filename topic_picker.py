import random

def pick_static_topic(config):
    static_list = config.get("topics", {}).get("static", [])
    if not static_list:
        raise ValueError("No static topics defined in config.")
    return random.choice(static_list)

def pick_topic(config, llm_pipeline):
    use_llm = config.get("topics", {}).get("use_llm_for_topic", False)
    if use_llm:
        seed = config.get("topics", {}).get("llm_topic_seed", "Give me a random topic.")
        prompt = f"{seed}\n\nRespond with a concise topic phrase only."
        raw = llm_pipeline.generate(prompt)
        # Simple sanitization: take first line, strip punctuation if excessive
        topic = raw.strip().split("\n")[0]
        return topic
    else:
        return pick_static_topic(config)
