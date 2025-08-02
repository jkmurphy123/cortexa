import os
import time
import random
from datetime import datetime

try:
    from llama_cpp import Llama
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

def dummy_generate(prompt, temperature=0.7, top_p=0.9, max_tokens=256):
    filler = (
        " The mind wanders like a loose thread. It thinks of roller coasters as emotion graphs, "
        "then briefly recalls a childhood smell. Suddenly a tangent about forgotten carnival mascots appears."
    )
    return f"{prompt} {filler}"

class LLMPipeline:
    def __init__(self, model_path=None, temperature=0.7, top_p=0.9, max_tokens=256):
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.model = None
        if LLM_AVAILABLE and model_path:
            try:
                self.model = Llama(model_path=model_path)
            except Exception as e:
                print(f"[warning] failed to load llama model: {e}")
                self.model = None

    def generate(self, prompt):
        if self.model:
            resp = self.model(
                prompt=prompt,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                stop=None,
            )
            return resp.get("choices", [{}])[0].get("text", "").strip()
        else:
            return dummy_generate(prompt, temperature=self.temperature, top_p=self.top_p)
