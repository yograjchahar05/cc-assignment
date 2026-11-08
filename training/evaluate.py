"""Evaluation script to run any model on validation.jsonl and produce score.py predictions."""
import argparse
import json
import os
import requests
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def query_ollama_teacher(teacher_url, model, sys_prompt, cmd, timeout=45):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Command: {cmd}\nJSON:"}
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "seed": 42,
            "num_predict": 40,
            "stop": ["\n\n", "Command:", "\nCommand", "}\n"],
            "num_thread": 8
        }
    }
    resp = requests.post(f"{teacher_url.rstrip('/')}/api/chat", json=payload, timeout=timeout)
    resp.raise_for_status()
    raw = resp.json().get("message", {}).get("content", "").strip()
    if raw.startswith("{") and not raw.endswith("}"):
        raw = raw + "}"
    if "}" in raw:
        raw = raw[:raw.index("}") + 1]
    return raw


def eval_teacher(val_file, prompt_file, out_file, teacher_url="http://localhost:11434", model="phi3.5"):
    with open(prompt_file, encoding="utf-8") as f:
        sys_prompt = f.read().strip()

    predictions = []
    # If partial predictions exist, resume from them
    seen_ids = set()
    if os.path.exists(out_file):
        with open(out_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        p = json.loads(line)
                        if "id" in p:
                            predictions.append(p)
                            seen_ids.add(p["id"])
                    except Exception:
                        pass
        print(f"Resuming teacher eval: {len(seen_ids)} already evaluated.", flush=True)

    items = []
    with open(val_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
    with open(out_file, "a", encoding="utf-8") as out:
        for idx, item in enumerate(items, 1):
            cid = item["id"]
            if cid in seen_ids:
                continue
            cmd = item["text"]

            try:
                raw_reply = query_ollama_teacher(teacher_url, model, sys_prompt, cmd)
            except Exception as e:
                print(f"Error querying teacher on {cid}: {e}", flush=True)
                raw_reply = ""

            pred = {"id": cid, "prediction": raw_reply}
            predictions.append(pred)
            out.write(json.dumps(pred) + "\n")
            out.flush()

            if len(predictions) % 10 == 0 or len(predictions) == len(items):
                print(f"Teacher evaluated: {len(predictions)}/{len(items)}", flush=True)

    print(f"Finished evaluating teacher. Total predictions: {len(predictions)} in {out_file}", flush=True)


def eval_local_model(model_path, val_file, out_file, max_new_tokens=64):
    print(f"Loading local model from {model_path}...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_path)
    model.eval()

    items = []
    with open(val_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    predictions = []
    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as out:
        for idx, item in enumerate(items, 1):
            cid = item["id"]
            cmd = item["text"]

            prompt = f"Command: {cmd}\nJSON: "
            inputs = tokenizer(prompt, return_tensors="pt")
            with torch.no_grad():
                out_ids = model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    pad_token_id=tokenizer.eos_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                    do_sample=False
                )

            gen_text = tokenizer.decode(out_ids[0], skip_special_tokens=True)
            if "JSON:" in gen_text:
                raw_out = gen_text.split("JSON:", 1)[1].strip()
            else:
                raw_out = gen_text[len(prompt):].strip()

            if "{" in raw_out and "}" in raw_out:
                brace_start = raw_out.index("{")
                brace_end = raw_out.rindex("}") + 1
                raw_out = raw_out[brace_start:brace_end]
            elif "}" in raw_out:
                raw_out = raw_out[:raw_out.index("}") + 1]

            pred = {"id": cid, "prediction": raw_out}
            predictions.append(pred)
            out.write(json.dumps(pred) + "\n")
            out.flush()

            if idx % 25 == 0 or idx == len(items):
                print(f"Evaluated: {idx}/{len(items)}", flush=True)

    print(f"Saved predictions to {out_file}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Evaluate models against validation set.")
    parser.add_argument("--mode", choices=["teacher", "local"], required=True)
    parser.add_argument("--model", default="EleutherAI/pythia-70m", help="Hugging Face model path or Ollama model name")
    parser.add_argument("--val_file", default="data/validation.jsonl")
    parser.add_argument("--prompt_file", default="prompts/teacher_prompt.txt")
    parser.add_argument("--out_file", required=True)
    args = parser.parse_args()

    if args.mode == "teacher":
        eval_teacher(args.val_file, args.prompt_file, args.out_file, model=args.model)
    else:
        eval_local_model(args.model, args.val_file, args.out_file)


if __name__ == "__main__":
    main()
