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
from topic_picker import pick_topic  # config-driven topics
from ui_renderer import QApplication, MainWindow
from PyQt5.QtCore import QObject, pyqtSignal

# Signal dispatcher to marshal chunks into the GUI thread
class ChunkDispatcher(QObject):
    chunk_signal = pyqtSignal(str, object)  # chunk text, threading.Event to signal completion

# Sentence-aware chunking
_sentence_splitter = re.compile(r'(?<=[.!?])\s+')

def chunk_by_sentence(text: str, max_words: int):
    sentences = _sentence_splitter.split(text.strip())
    current_chunk, current_count = [], 0

    def flush():
        if current_chunk:
            yield " ".join(current_chunk).strip()

    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue
        if current_count + len(words) <= max_words:
            current_chunk.append(sentence)
            current_count += len(words)
        else:
            yield from flush()
            current_chunk, current_count = [], 0
            if len(words) <= max_words:
                current_chunk, current_count = [sentence], len(words)
            else:
                for i in range(0, len(words), max_words):
                    yield " ".join(words[i:i+max_words]).strip()
                current_chunk, current_count = [], 0
    yield from flush()

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def setup_logger(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    rand = random.randint(1000, 9999)
    path = os.path.join(log_dir, f"conv_{timestamp}_{rand}.log")
    logger = logging.getLogger("streamer")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(path, encoding="utf-8")
    fmt = logging.Formatter("%Y-%m-%d %H:%M:%S [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger

def build_prompt(personality, topic, history_chunks, config):
    persona = (personality.get("prompt_persona") or personality.get("prompt_prefix", "")).strip()
    style_rules = personality.get("style_rules", [])
    examples = personality.get("examples", [])
    display_name = personality.get("display_name", personality.get("name", "Persona"))

    rules_block = "Style rules:\n" + "\n".join(f"- {r}" for r in style_rules) if style_rules else ""
    examples_block = "Examples:\n" + "\n".join(f"- {e}" for e in examples[:2]) if examples else ""
    short_history = "\n\n".join(history_chunks[-2:]) if history_chunks else ""
    reminder = f"Reminder: stay fully in character as {display_name}. No instructions or meta."

    parts = [
        f"Persona:\n{persona}",
        rules_block,
        examples_block,
        f"Topic: {topic}",
        (f"Previous thoughts:\n{short_history}" if short_history else ""),
        reminder,
        "Task: Continue a stream-of-consciousness monologue about the topic, in character.",
        "Begin:",
    ]
    return "\n\n".join(p for p in parts if p.strip())

def maybe_inject_tangent(chunk_count, drift_interval, config):
    if drift_interval and chunk_count > 0 and chunk_count % drift_interval == 0:
        return config.get("streaming", {}).get("tangent_prompt", "")
    return None

def backend_loop(personality, topic, llm, config, logger, stop_event, dispatcher):
    s = config.get("streaming", {})
    log_cfg = config.get("logging", {})

    max_words = personality.get("max_words_per_chunk", s.get("max_words_per_chunk", 60))
    inter_chunk_pause = s.get("inter_chunk_pause_seconds", 2.0)
    drift_interval = s.get("drift_interval_chunks", 4)
    max_history = s.get("max_history_chunks", 5)

    history, chunk_counter = [], 0
    logger.info(f"Starting stream with personality '{personality.get('display_name')}' on topic '{topic}'")
    time.sleep(s.get("initial_pause_seconds", 1.0))

    iteration = 0
    while not stop_event.is_set() and iteration < 8:
        iteration += 1
        tangent = maybe_inject_tangent(chunk_counter, drift_interval, config)
        prompt = (f"{tangent}\n\nThen continue in character about {topic}."
                  if tangent else build_prompt(personality, topic, history, config))

        if log_cfg.get("include_full_prompts", False):
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
            history.append(chunk)
            if len(history) > max_history:
                history = history[-max_history:]
            done.wait()
            time.sleep(inter_chunk_pause)

    logger.info("Backend loop finished.")

def main():
    parser = argparse.ArgumentParser(description="Phase 3: GUI streamer (PyQt5)")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    personalities = config.get("personalities", [])
    if not personalities:
        raise RuntimeError("No personalities in config.")

    personality = random.choice(personalities)

    # Topics from config (with optional LLM fallback if you want)
    topic_llm = LLMPipeline(
        model_path=args.model,
        temperature=config.get("streaming", {}).get("temperature", 0.8),
        top_p=config.get("streaming", {}).get("top_p", 0.9),
        max_tokens=64,
    )
    topic = pick_topic(config, topic_llm)

    logger = setup_logger(config.get("logging", {}).get("directory", "logs"))
    logger.info(f"Chosen personality: {personality.get('display_name')} topic: {topic}")

    llm = LLMPipeline(
        model_path=args.model,
        temperature=float(config.get("streaming", {}).get("temperature", 0.65)),
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

    ret = app.exec_()  # PyQt5 uses exec_()
    stop_event.set()
    backend_thread.join()
    sys.exit(ret)

if __name__ == "__main__":
    main()
