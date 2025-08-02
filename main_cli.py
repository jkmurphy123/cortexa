import yaml
import random
import time
import textwrap
import argparse
import sys

# Try importing llama-cpp-python; if not available, fall back to dummy generator.
try:
    from llama_cpp import Llama
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def pick_random_personality(config):
    return random.choice(config["personalities"])

def pick_random_topic(config):
    return random.choice(config["topics"])

def build_prompt(personality, topic, continuation=None):
    prefix = personality.get("prompt_prefix", "").strip()
    base = f"{prefix}\n\nTopic: {topic}\n\nStream of consciousness:"
    if continuation:
        base += f"\nContinue from previous: {continuation.strip()}"
    return base.strip()

def chunk_text(text, max_words):
    words = text.split()
    for i in range(0, len(words), max_words):
        yield " ".join(words[i : i + max_words])

def dummy_llm_generate(prompt, max_tokens=200):
    # Simple stub: echo the prompt with some variation to allow development before real model.
    filler = (
        " ...and then the thoughts drift like leaves on a pond, considering the absurdity of it all. "
        "There is a sudden tangent about how roller coasters resemble emotional ups and downs, "
        "and the memory of a long-forgotten summer flickers."
    )
    return f"{prompt} {filler}"

class LLMPipeline:
    def __init__(self, config, model_path=None):
        self.config = config
        self.model = None
        if LLM_AVAILABLE and model_path:
            try:
                self.model = Llama(model_path=model_path)
            except Exception as e:
                print(f"[warning] Failed to load LLM model at '{model_path}': {e}")
                self.model = None

    def generate(self, prompt, temperature=0.7, top_p=0.9, max_tokens=256):
        if self.model:
            resp = self.model(prompt=prompt,
                              temperature=temperature,
                              top_p=top_p,
                              max_tokens=max_tokens,
                              stop=None)
            # llama-cpp-python returns dict-like; extract generated text
            return resp.get("choices", [{}])[0].get("text", "").strip()
        else:
            return dummy_llm_generate(prompt)

def main():
    parser = argparse.ArgumentParser(description="Phase 1: Personality stream CLI prototype")
    parser.add_argument("--config", "-c", default="config.yaml", help="Path to YAML config file")
    parser.add_argument("--model", "-m", default=None, help="Path to ggml model for llama.cpp (optional)")
    parser.add_argument("--iterations", "-n", type=int, default=3, help="Number of continuation iterations")
    args = parser.parse_args()

    config = load_config(args.config)
    personality = pick_random_personality(config)
    topic = pick_random_topic(config)
    streaming_cfg = config.get("streaming", {})

    max_words_per_chunk = streaming_cfg.get("max_words_per_chunk", 50)
    initial_pause = streaming_cfg.get("initial_pause_seconds", 1.0)
    inter_chunk_pause = streaming_cfg.get("inter_chunk_pause_seconds", 1.0)
    temperature = streaming_cfg.get("temperature", 0.7)
    top_p = streaming_cfg.get("top_p", 0.9)

    print(f"Selected personality: {personality.get('display_name', personality['name'])}")
    print(f"Selected topic: {topic}")
    print()

    llm = LLMPipeline(config, model_path=args.model)

    # Initial prompt
    prompt = build_prompt(personality, topic)
    print("[Generating initial exploration...]\n")
    time.sleep(initial_pause)
    output = llm.generate(prompt, temperature=temperature, top_p=top_p)

    # Stream out the first response in chunks
    for chunk in chunk_text(output, max_words_per_chunk):
        #print(chunk)
        time.sleep(inter_chunk_pause)
    last_fragment = output  # naive: use entire output for continuation context

    # Continuations
    for i in range(1, args.iterations + 1):
        continuation_prompt = build_prompt(personality, topic, continuation=last_fragment)
        print(f"\n[Continuation {i}...]\n")
        time.sleep(inter_chunk_pause)
        output = llm.generate(continuation_prompt, temperature=temperature, top_p=top_p)
        for chunk in chunk_text(output, max_words_per_chunk):
            #print(chunk)
            time.sleep(inter_chunk_pause)
        last_fragment = output  # in a real system you'd manage rolling context more carefully

if __name__ == "__main__":
    main()
