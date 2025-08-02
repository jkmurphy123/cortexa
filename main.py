import yaml
import random
import time
import argparse
import os
import logging
from datetime import datetime
from llm_interface import LLMPipeline
from topic_picker import pick_topic

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def setup_logger(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    rand = random.randint(1000, 9999)
    fname = f"conv_{timestamp}_{rand}.log"
    fullpath = os.path.join(log_dir, fname)
    logger = logging.getLogger("streamer")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(fullpath, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # also echo to console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger

def chunk_text(text, max_words):
    words = text.split()
    for i in range(0, len(words), max_words):
        yield " ".join(words[i : i + max_words])

def build_prompt(personality, topic, history_chunks, config):
    prefix = personality.get("prompt_prefix", "").strip()
    base = f"{prefix}\n\nTopic: {topic}\n\n"
    if not history_chunks:
        base += "Begin a stream of consciousness exploring the topic. Let thoughts flow, include associations and mild tangents."
    else:
        # include recent context
        context = "\n\n".join(history_chunks)
        base += (
            "Continue the stream of consciousness. Previous few thoughts:\n"
            f"{context}\n\n"
            "Let your mind drift naturally, staying in character, and explore related ideas."
        )
    return base.strip()

def maybe_inject_tangent(chunk_count, drift_interval, config):
    if drift_interval and chunk_count > 0 and chunk_count % drift_interval == 0:
        return config.get("streaming", {}).get("tangent_prompt", "")
    return None

def main():
    parser = argparse.ArgumentParser(description="Phase 2: Personality/topic streamer CLI")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--model", "-m", default=None, help="Path to gguf/ggml model for llama.cpp")
    parser.add_argument("--max_iterations", "-n", type=int, default=5, help="Total number of generation turns")
    args = parser.parse_args()

    config = load_config(args.config)
    personalities = config.get("personalities", [])
    if not personalities:
        raise RuntimeError("No personalities defined in config.")

    personality = random.choice(personalities)
    streaming_cfg = config.get("streaming", {})
    logging_cfg = config.get("logging", {})

    # Logger
    log_dir = logging_cfg.get("directory", "logs")
    logger = setup_logger(log_dir)
    logger.info(f"Using personality: {personality.get('display_name', personality['name'])}")

    # Topic selection
    llm_for_topic = LLMPipeline(
        model_path=args.model,
        temperature=streaming_cfg.get("temperature", 0.7),
        top_p=streaming_cfg.get("top_p", 0.9),
        max_tokens=128,
    )
    topic = pick_topic(config, llm_for_topic)
    logger.info(f"Selected topic: {topic}")

    # Main LLM pipeline (could be same or separately parameterized)
    llm = LLMPipeline(
        model_path=args.model,
        temperature=streaming_cfg.get("temperature", 0.7),
        top_p=streaming_cfg.get("top_p", 0.9),
        max_tokens=256,
    )

    max_words = streaming_cfg.get("max_words_per_chunk", 60)
    initial_pause = streaming_cfg.get("initial_pause_seconds", 1.0)
    inter_chunk_pause = streaming_cfg.get("inter_chunk_pause_seconds", 2.0)
    drift_interval = streaming_cfg.get("drift_interval_chunks", 4)
    max_history = streaming_cfg.get("max_history_chunks", 5)

    history = []  # recent output chunks for context window
    chunk_counter = 0

    logger.info("Beginning stream of consciousness...")
    time.sleep(initial_pause)

    for iteration in range(1, args.max_iterations + 1):
        # maybe inject tangent
        tangent = maybe_inject_tangent(chunk_counter, drift_interval, config)
        if tangent:
            prompt = f"{tangent}\n\nThen continue the stream in character about {topic}."
        else:
            prompt = build_prompt(personality, topic, history, config)

        if logging_cfg.get("include_full_prompts", False):
            logger.debug(f"Prompt (iteration {iteration}):\n{prompt}")

        raw_output = llm.generate(prompt)
        if not raw_output:
            logger.warning("LLM returned empty output; skipping.")
            continue

        # Split and display
        for chunk in chunk_text(raw_output, max_words):
            chunk_counter += 1
            print(chunk + "\n")
            logger.info(f"Chunk {chunk_counter}: {chunk}")
            # Update history window
            history.append(chunk)
            if len(history) > max_history:
                history = history[-max_history :]
            time.sleep(inter_chunk_pause)

    logger.info("Stream completed.")

if __name__ == "__main__":
    main()
