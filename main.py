import yaml
import random
import time
import argparse
import os
import logging
import threading
import sys
import re
from datetime import datetime

from llm_interface import LLMPipeline

from ui_renderer import QApplication, MainWindow
from PyQt6.QtCore import QObject, pyqtSignal

# Signal dispatcher to marshal chunks into the GUI thread
class ChunkDispatcher(QObject):
    chunk_signal = pyqtSignal(str, object)  # chunk text, threading.Event to signal completion

_sentence_splitter = re.compile(r'(?<=[.!?])\s+')

def chunk_by_sentence(text: str, max_words: int):
    """
    Yield chunks of text that end on sentence boundaries without exceeding max_words.
    If a single sentence is longer than max_words, fallback to word-level slicing for that sentence.
    """
    sentences = _sentence_splitter.split(text.strip())
    current_chunk = []
    current_count = 0

    def yield_current():
        if current_chunk:
            yield " ".join(current_chunk).strip()

    for sentence in sentences:
        words_in_sentence = sentence.split()
        if not words_in_sentence:
            continue
        if current_count + len(words_in_sentence) <= max_words:
            current_chunk.append(sentence)
            current_count += len(words_in_sentence)
        else:
            yield from yield_current()
            current_chunk = []
            current_count = 0
            if len(words_in_sentence) <= max_words:
                current_chunk = [sentence]
                current_count = len(words_in_sentence)
            else:
                # sentence itself too big: break it into word chunks
                words = words_in_sentence
                for i in range(0, len(words), max_words):
                    part = " ".join(words[i : i + max_words])
                    yield part.strip()
                current_chunk = []
                current_count = 0
    yield from yield_current()


def pick_topic_via_llm(config, llm_pipeline):
    """
    Always uses the LLM to generate a topic based on the seed prompt.
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

def sanitize_topic(raw: str) -> str:
    # Take first non-empty line
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    line = lines[0]
    # Strip surrounding quotes
    line = re.sub(r'^["\']+|["\']+$', '', line).strip()
    # Truncate if too long
    if len(line) > 100:
        line = line[:100].rsplit(" ", 1)[0]
    return line

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
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger

def build_prompt(personality, topic, history_chunks, config):
    prefix = personality.get("prompt_prefix", "").strip()
    base = f"{prefix}\n\nTopic: {topic}\n\n"
    if not history_chunks:
        base += "Begin a stream of consciousness exploring the topic. Let thoughts flow, include associations and mild tangents."
    else:
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

def backend_loop(personality, topic, llm, config, logger, stop_event, dispatcher):
    streaming_cfg = config.get("streaming", {})
    logging_cfg = config.get("logging", {})

    max_words = personality.get("max_words_per_chunk", streaming_cfg.get("max_words_per_chunk", 60))
    inter_chunk_pause = streaming_cfg.get("inter_chunk_pause_seconds", 2.0)
    drift_interval = streaming_cfg.get("drift_interval_chunks", 4)
    max_history = streaming_cfg.get("max_history_chunks", 5)

    history = []
    chunk_counter = 0

    logger.info(f"Starting stream with personality '{personality.get('display_name')}' on topic '{topic}'")
    time.sleep(streaming_cfg.get("initial_pause_seconds", 1.0))

    iteration = 0
    while not stop_event.is_set() and iteration < 8:  # adjust cap as desired
        iteration += 1
        tangent = maybe_inject_tangent(chunk_counter, drift_interval, config)
        if tangent:
            prompt = f"{tangent}\n\nThen continue the stream in character about {topic}."
        else:
            prompt = build_prompt(personality, topic, history, config)

        if logging_cfg.get("include_full_prompts", False):
            logger.debug(f"Prompt iteration {iteration}:\n{prompt}")

        raw_output = llm.generate(prompt)
        if not raw_output:
            logger.warning("Empty LLM output; skipping iteration.")
            continue

        for chunk in chunk_by_sentence(raw_output, max_words):
            chunk_counter += 1
            done = threading.Event()
            dispatcher.chunk_signal.emit(chunk, done)
            logger.info(f"Chunk {chunk_counter}: {chunk}")

            # update history window
            history.append(chunk)
            if len(history) > max_history:
                history = history[-max_history:]
            # wait for UI typing to finish before continuing
            done.wait()
            time.sleep(inter_chunk_pause)

    logger.info("Backend loop finished.")

def main():
    parser = argparse.ArgumentParser(description="Phase 3: GUI streamer (LLM-derived topics)")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    personalities = config.get("personalities", [])
    if not personalities:
        raise RuntimeError("No personalities in config.")

    personality = random.choice(personalities)

    # LLM to generate topic
    topic_picker_llm = LLMPipeline(
        model_path=args.model,
        temperature=config.get("streaming", {}).get("temperature", 0.8),  # slightly higher diversity for topic
        top_p=config.get("streaming", {}).get("top_p", 0.9),
        max_tokens=64,
    )
    topic = pick_topic_via_llm(config, topic_picker_llm)

    logger = setup_logger(config.get("logging", {}).get("directory", "logs"))
    logger.info(f"Chosen personality: {personality.get('display_name')} topic: {topic}")

    # Main generation LLM
    llm = LLMPipeline(
        model_path=args.model,
        temperature=config.get("streaming", {}).get("temperature", 0.7),
        top_p=config.get("streaming", {}).get("top_p", 0.9),
        max_tokens=256,
    )

    screen_width = config.get("screen_width", 1024)
    screen_height = config.get("screen_height", 768)
    images_dir = config.get("ui", {}).get("images_dir", "ui/images")

    app = QApplication(sys.argv)
    window = MainWindow(
        personality,
        topic,
        images_dir=images_dir,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    window.showFullScreen()

    # Dispatcher and slot
    dispatcher = ChunkDispatcher()

    def handle_chunk(chunk, done_event):
        def on_complete():
            done_event.set()
        inter_chunk_pause = config.get("streaming", {}).get("inter_chunk_pause_seconds", 2.0)
        window.display_chunk_with_typing(chunk, inter_chunk_pause, on_complete=on_complete)

    dispatcher.chunk_signal.connect(handle_chunk)

    stop_event = threading.Event()
    backend_thread = threading.Thread(
        target=backend_loop,
        args=(personality, topic, llm, config, logger, stop_event, dispatcher),
        daemon=True,
    )
    backend_thread.start()

    ret = app.exec()
    stop_event.set()
    backend_thread.join()
    sys.exit(ret)

if __name__ == "__main__":
    main()
