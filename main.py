import yaml
import random
import time
import argparse
import os
import logging
from datetime import datetime
import threading
import sys

from llm_interface import LLMPipeline
from topic_picker import pick_topic

from ui_renderer import QApplication, MainWindow

class ChunkDispatcher(QObject):
    # chunk text, and a Python object (the threading.Event) to signal completion
    chunk_signal = pyqtSignal(str, object)

# Logging setup (reuse from phase2)
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

def backend_loop(personality, topic, llm, config, window, logger, stop_event, dispatcher):
    streaming_cfg = config.get("streaming", {})
    max_words = personality.get("speech_balloon", {}).get("max_words_per_chunk", streaming_cfg.get("max_words_per_chunk", 60))
    inter_chunk_pause = streaming_cfg.get("inter_chunk_pause_seconds", 2.0)
    drift_interval = streaming_cfg.get("drift_interval_chunks", 4)
    max_history = streaming_cfg.get("max_history_chunks", 5)

    history = []
    chunk_counter = 0

    logger.info(f"Starting stream with personality '{personality.get('display_name')}' on topic '{topic}'")
    time.sleep(streaming_cfg.get("initial_pause_seconds", 1.0))

    iteration = 0
    while not stop_event.is_set() and iteration < 8:
        iteration += 1
        tangent = maybe_inject_tangent(chunk_counter, drift_interval, config)
        if tangent:
            prompt = f"{tangent}\n\nThen continue the stream in character about {topic}."
        else:
            prompt = build_prompt(personality, topic, history, config)

        if config.get("logging", {}).get("include_full_prompts", False):
            logger.debug(f"Prompt iteration {iteration}:\n{prompt}")

        raw_output = llm.generate(prompt)
        if not raw_output:
            logger.warning("Empty LLM output; skipping iteration.")
            continue

        for chunk in chunk_text(raw_output, max_words):
            chunk_counter += 1
            done = threading.Event()
            # emit into main thread; handler will call display_chunk_with_typing and set done when finished
            dispatcher.chunk_signal.emit(chunk, done)
            logger.info(f"Chunk {chunk_counter}: {chunk}")
            history.append(chunk)
            if len(history) > max_history:
                history = history[-max_history:]
            # wait for the UI typing animation to complete
            done.wait()
            time.sleep(inter_chunk_pause)

    logger.info("Backend loop finished.")

def main():
    parser = argparse.ArgumentParser(description="Phase 3: GUI streamer")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    personalities = config.get("personalities", [])
    if not personalities:
        raise RuntimeError("No personalities in config.")

    personality = random.choice(personalities)
    topic_picker_llm = LLMPipeline(
        model_path=args.model,
        temperature=config.get("streaming", {}).get("temperature", 0.7),
        top_p=config.get("streaming", {}).get("top_p", 0.9),
        max_tokens=128,
    )
    topic = pick_topic(config, topic_picker_llm)

    logger = setup_logger(config.get("logging", {}).get("directory", "logs"))
    logger.info(f"Chosen personality: {personality.get('display_name')} topic: {topic}")

    llm = LLMPipeline(
        model_path=args.model,
        temperature=config.get("streaming", {}).get("temperature", 0.7),
        top_p=config.get("streaming", {}).get("top_p", 0.9),
        max_tokens=256,
    )

    dispatcher = ChunkDispatcher()

    def handle_chunk(chunk, done_event):
        def on_complete():
            done_event.set()
        # Assuming inter_chunk_pause is available in this scope or pass it in as needed
        window.display_chunk_with_typing(chunk, config["streaming"].get("inter_chunk_pause_seconds", 2.0), on_complete=on_complete)

    dispatcher.chunk_signal.connect(handle_chunk)

    app = QApplication(sys.argv)
    window = MainWindow(personality, topic)
    window.show()

    stop_event = threading.Event()
    backend_thread = threading.Thread(
        target=backend_loop,
        args=(personality, topic, llm, config, window, logger, stop_event, dispatcher),
        daemon=True,
    )
    backend_thread.start()

    ret = app.exec()
    stop_event.set()
    backend_thread.join()
    sys.exit(ret)

if __name__ == "__main__":
    main()
