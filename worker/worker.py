"""Worker script for parallel teacher labelling.

Reads environment variables:
  SHARD_INDEX: integer >= 0 (this worker's index)
  SHARD_COUNT: integer >= 1 (total number of workers/shards)
  TEACHER_URL: base URL for Ollama teacher (default: http://localhost:11434)
  MODEL_NAME: model name (default: phi3.5)
  INPUT_FILE: path to commands pool (default: data/commands_pool.jsonl)
  PROMPT_FILE: path to teacher prompt (default: prompts/teacher_prompt.txt)
  OUTPUT_DIR: directory to save shard outputs (default: datasets/teacher)
  S3_ENDPOINT: optional S3 endpoint to upload shard object
  S3_BUCKET: S3 bucket name (default: datasets)

Each worker takes commands whose line index % SHARD_COUNT == SHARD_INDEX.
Writes {"id": "...", "text": "...", "teacher_raw": "..."} to shard-{SHARD_INDEX}.jsonl
"""
import json
import logging
import os
import sys
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def get_env_int(key, default):
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        sys.exit(f"Environment variable {key} must be an integer, got: {val}")


def query_teacher(teacher_url, model, prompt_template, command_text, timeout=60):
    """Query the Ollama teacher model with temperature=0 and seed=42."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt_template},
            {"role": "user", "content": f"Command: {command_text}\nJSON:"}
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
    url = f"{teacher_url.rstrip('/')}/api/chat"
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    raw = resp.json().get("message", {}).get("content", "").strip()
    if raw.startswith("{") and not raw.endswith("}"):
        raw = raw + "}"
    if "}" in raw:
        raw = raw[:raw.index("}") + 1]
    return raw


def upload_to_s3(endpoint, bucket, key, local_file):
    """Upload shard output to S3/SeaweedFS if configured."""
    try:
        import boto3
        from botocore.config import Config
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "any"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "any"),
            config=Config(signature_version="s3v4")
        )
        s3.upload_file(local_file, bucket, key)
        logging.info(f"Uploaded {local_file} to s3://{bucket}/{key}")
    except Exception as e:
        logging.warning(f"Could not upload to S3: {e}")


def main():
    shard_index = get_env_int("SHARD_INDEX", 0)
    shard_count = get_env_int("SHARD_COUNT", 2)
    teacher_url = os.environ.get("TEACHER_URL", "http://localhost:11434")
    model_name = os.environ.get("MODEL_NAME", "phi3.5")
    input_file = os.environ.get("INPUT_FILE", "data/commands_pool.jsonl")
    prompt_file = os.environ.get("PROMPT_FILE", "prompts/teacher_prompt.txt")
    output_dir = os.environ.get("OUTPUT_DIR", "datasets/teacher")
    s3_endpoint = os.environ.get("S3_ENDPOINT", "")
    s3_bucket = os.environ.get("S3_BUCKET", "datasets")

    logging.info(f"Starting worker: SHARD_INDEX={shard_index}, SHARD_COUNT={shard_count}")

    if not os.path.isfile(prompt_file):
        sys.exit(f"Prompt file not found: {prompt_file}")
    with open(prompt_file, encoding="utf-8") as f:
        prompt_template = f.read().strip()

    if not os.path.isfile(input_file):
        sys.exit(f"Input file not found: {input_file}")

    os.makedirs(output_dir, exist_ok=True)
    shard_filename = f"shard-{shard_index}.jsonl"
    output_path = os.path.join(output_dir, shard_filename)

    assigned_items = []
    with open(input_file, encoding="utf-8") as f:
        for line_idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            if line_idx % shard_count == shard_index:
                assigned_items.append((line_idx, json.loads(line)))

    logging.info(f"Worker {shard_index}: assigned {len(assigned_items)} commands")

    # Read already processed IDs to allow resuming if interrupted
    processed_ids = set()
    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        if "id" in record:
                            processed_ids.add(record["id"])
                    except json.JSONDecodeError:
                        pass
        logging.info(f"Worker {shard_index}: found {len(processed_ids)} already processed records")

    with open(output_path, "a", encoding="utf-8") as out_f:
        for count, (line_idx, item) in enumerate(assigned_items, 1):
            cmd_id = item["id"]
            cmd_text = item["text"]
            if cmd_id in processed_ids:
                continue

            try:
                raw_reply = query_teacher(teacher_url, model_name, prompt_template, cmd_text)
            except Exception as e:
                logging.error(f"Error querying teacher for {cmd_id}: {e}")
                raw_reply = ""

            record = {
                "id": cmd_id,
                "text": cmd_text,
                "teacher_raw": raw_reply
            }
            out_f.write(json.dumps(record) + "\n")
            out_f.flush()

            if count % 50 == 0 or count == len(assigned_items):
                logging.info(f"Worker {shard_index}: processed {count}/{len(assigned_items)}")

    logging.info(f"Worker {shard_index}: finished writing to {output_path}")

    if s3_endpoint:
        s3_key = f"teacher/shard-{shard_index}.jsonl"
        upload_to_s3(s3_endpoint, s3_bucket, s3_key, output_path)


if __name__ == "__main__":
    main()
