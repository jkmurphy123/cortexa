# cortexa
An AI musing to itself using a local LLM

One-Time Setup

cd projects
python3 -m venv llm_env --system-site-packages

Running App

cd projects
source llm_env/bin/activate
cd cortexa

python main.py

to test connectivity

# (activate your venv first)
python test_llm.py --model /home/ubuntu/models/qwen2-7b-instruct-q5_k_m.gguf --prompt "Say 'It works.' then describe one fun fact about acorns." --n-predict 64 --temp 0.7 --top-p 0.9 --ctx 2048 --verbose

