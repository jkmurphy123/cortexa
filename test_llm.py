#!/usr/bin/env python3
"""
Minimal standalone LLM connectivity test for llama-cpp-python.

Usage:
  python test_llm.py --model /path/to/model.gguf [--prompt "hello"] [--n-predict 64] [--temp 0.7] [--top-p 0.9] [--ctx 2048] [--dump-json]

Exit codes:
  0 = success
  1 = bad args / missing files
  2 = import failure (llama_cpp)
  3 = model load failure
  4 = generation failure
"""
import argparse
import json
import logging
import os
import platform
import time
from pathlib import Path
from typing import Optional

LOG = logging.getLogger("llm-test")


def setup_logging(verbose: bool):
    LOG.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    ch.setFormatter(fmt)
    LOG.addHandler(ch)


def human_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def check_env():
    LOG.info("Python: %s", platform.python_version())
    LOG.info("Platform: %s %s (%s)", platform.system(), platform.release(), platform.machine())
    for var in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "GGML_NUM_THREADS"]:
        if var in os.environ:
            LOG.info("Env %s=%s", var, os.environ[var])


def validate_model_path(model_path: Path) -> Optional[str]:
    if not model_path.exists():
        return f"Model not found: {model_path}"
    if not model_path.is_file():
        return f"Model path is not a file: {model_path}"
    try:
        size = model_path.stat().st_size
        if size < 50 * 1024 * 1024:  # 50MB
            return f"Model file looks too small ({human_bytes(size)}): {model_path}"
        LOG.info("Model file: %s (%s)", model_path, human_bytes(size))
    except Exception as e:
        return f"Could not stat model file: {e}"
    try:
        with open(model_path, "rb") as f:
            f.read(64)
    except Exception as e:
        return f"Model not readable: {e}"
    return None


def import_llama():
    try:
        import llama_cpp  # noqa
        from llama_cpp import Llama
        return Llama, llama_cpp
    except Exception as e:
        LOG.error("Failed to import llama_cpp: %s", e)
        LOG.info("Tip: pip install --upgrade llama-cpp-python")
        raise


def main():
    ap = argparse.ArgumentParser(description="llama-cpp-python smoke test")
    ap.add_argument("--model", "-m", required=True, help="Path to .gguf model")
    ap.add_argument("--prompt", "-p", default="Say 'It works.' then tell me one fun fact about squirrels.",
                    help="Prompt to send")
    ap.add_argument("--n-predict", "-n", type=int, default=64, help="Max tokens to generate")
    ap.add_argument("--temp", type=float, default=0.7)
    ap.add_argument("--top-p", type=float, default=0.9)
    ap.add_argument("--ctx", type=int, default=2048, help="Context window size")
    ap.add_argument("--threads", type=int, default=0, help="Override n_threads (0 = auto)")
    ap.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    ap.add_argument("--dump-json", action="store_true", help="Print raw JSON response at end")
    args = ap.parse_args()

    setup_logging(args.verbose)
    check_env()

    model_path = Path(args.model).expanduser().resolve()
    err = validate_model_path(model_path)
    if err:
        LOG.error(err)
        return 1

    # Import llama_cpp and report build info
    try:
        Llama, llama_cpp = import_llama()
    except Exception:
        return 2

    LOG.info("llama_cpp version: %s", getattr(llama_cpp, "__version__", "unknown"))
    build = getattr(llama_cpp, "llama_print_system_info", None)
    if build:
        try:
            # Note: some builds print directly to stdout; we still call for visibility
            LOG.info("---- llama system info ----")
            print(build().strip())
            LOG.info("---------------------------")
        except Exception as e:
            LOG.warning("Could not fetch llama system info: %s", e)

    # Instantiate model
    init_kwargs = dict(
        model_path=str(model_path),
        n_ctx=args.ctx,
    )
    if args.threads and args.threads > 0:
        init_kwargs["n_threads"] = int(args.threads)

    LOG.info("Loading model with args: %s", init_kwargs)
    t0 = time.time()
    try:
        llm = Llama(**init_kwargs)  # may take time on first load
    except Exception as e:
        LOG.error("Failed to load model: %s", e)
        LOG.info("Troubleshooting tips:")
        LOG.info(" - Ensure the file is a GGUF model compatible with your llama-cpp-python version.")
        LOG.info(" - Try a smaller/less-quantized model variant if running out of memory.")
        LOG.info(" - On Raspberry Pi, ensure enough swap and free RAM; close other apps.")
        LOG.info(" - If you built from source, check BLAS and NEON options are sane.")
        return 3
    t_load = time.time() - t0
    LOG.info("Model loaded in %.2fs", t_load)

    # Tokenize a probe first (fast error surface)
    probe = "Hello"
    try:
        toks = llm.tokenize(probe.encode("utf-8"))
        LOG.info("Tokenization OK: %r -> %s tokens", probe, len(toks))
    except Exception as e:
        LOG.error("Tokenization failed: %s", e)
        return 3

    # Build a clearly delimited prompt to see boundaries in output
    user_prompt = f"<<BEGIN PROMPT>>\n{args.prompt.strip()}\n<<END PROMPT>>\nResponse:"
    LOG.info("Prompt: %s", user_prompt.replace("\n", "\\n"))

    # Run a short generation
    gen_kwargs = dict(
        prompt=user_prompt,
        max_tokens=args.n_predict,
        temperature=args.temp,
        top_p=args.top_p,
        stop=None,          # you can add ["<<END>>"] if your model uses special tokens
        echo=False,
    )
    LOG.info("Generating with: %s", gen_kwargs)

    t1 = time.time()
    try:
        out = llm(**gen_kwargs)
    except Exception as e:
        LOG.error("Generation failed: %s", e)
        LOG.info("If this is OOM, try: --n-predict 32 --ctx 1024 --threads 2")
        return 4
    t_gen = time.time() - t1

    # Parse output
    text = ""
    try:
        choices = out.get("choices", [])
        if choices:
            text = choices[0].get("text", "")
    except Exception as e:
        LOG.warning("Could not parse choices from output: %s", e)

    # Stats if available
    usage = out.get("usage", {}) if isinstance(out, dict) else {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")

    LOG.info("----- RESULT -----")
    LOG.info("Response (truncated to 500 chars): %s", text[:500].replace("\n", "\\n"))
    LOG.info("Generation time: %.2fs", t_gen)
    if prompt_tokens is not None:
        LOG.info("Tokens: prompt=%s, completion=%s, total=%s", prompt_tokens, completion_tokens, total_tokens)

    if args.dump_json:
        try:
            print("\nRAW JSON:\n", json.dumps(out, indent=2) if isinstance(out, dict) else out)
        except Exception:
            print("\nRAW OUT (unserializable):\n", out)

    LOG.info("Test completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
