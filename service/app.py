"""FastAPI inference service for command parsing.

Endpoints:
  POST /parse: body {"text": "..."} -> 200 with 4-key JSON or 500 on validation failure
  GET /healthz: 200 while alive
  GET /readyz: 503 while loading, 200 once ready

Headers on POST /parse:
  X-Model-Version: MODEL_VERSION
  X-Served-By: Pod name / Hostname
"""
import json
import logging
import os
import socket
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load schema.json
SCHEMA_PATH = os.environ.get("SCHEMA_PATH", "data/schema.json")
if not os.path.exists(SCHEMA_PATH):
    # Try looking in parent dir if running inside service/
    alt_schema = os.path.join(os.path.dirname(__file__), "..", "data", "schema.json")
    if os.path.exists(alt_schema):
        SCHEMA_PATH = alt_schema

try:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        SCHEMA_DATA = json.load(f)
    VALID_INTENTS = set(SCHEMA_DATA.get("intents", []))
    REQUIRED_KEYS = set(SCHEMA_DATA.get("keys", ["intent", "date", "time", "place"]))
except Exception as e:
    logging.warning(f"Could not load schema from {SCHEMA_PATH}: {e}")
    VALID_INTENTS = {
        "alarm_set", "alarm_query", "calendar_set", "calendar_query",
        "calendar_remove", "weather_query", "datetime_query", "recommendation_events"
    }
    REQUIRED_KEYS = {"intent", "date", "time", "place"}

# Service state
is_ready = False
model = None
tokenizer = None
pod_name = os.environ.get("POD_NAME") or os.environ.get("HOSTNAME") or socket.gethostname()
model_version = os.environ.get("MODEL_VERSION", "v1")
max_new_tokens = int(os.environ.get("MAX_NEW_TOKENS", "128"))
fault_inject = os.environ.get("FAULT_INJECT", "0")


def validate_prediction(raw_output: str):
    """Validate model output against schema.json.
    Returns (True, parsed_dict) or (False, None).
    """
    if fault_inject == "1" or os.environ.get("FAULT_INJECT", "0") == "1":
        raw_output = "not json"

    try:
        data = json.loads(str(raw_output).strip())
    except Exception:
        return False, None

    if not isinstance(data, dict):
        return False, None

    if set(data.keys()) != REQUIRED_KEYS:
        return False, None

    if data.get("intent") not in VALID_INTENTS:
        return False, None

    for slot in ("date", "time", "place"):
        val = data.get(slot)
        if val is not None and not isinstance(val, str):
            return False, None

    return True, data


def download_s3_prefix(endpoint_url, s3_uri, local_dest):
    """Download all files from s3://bucket/prefix into local_dest."""
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")

    os.makedirs(local_dest, exist_ok=True)
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "seaweedfs")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "seaweedfs")

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4")
    )

    paginator = s3.get_paginator("list_objects_v2")
    found_any = False
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel_path = os.path.relpath(key, prefix) if prefix else key
            dest_file = os.path.join(local_dest, rel_path)
            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            logging.info(f"Downloading s3://{bucket}/{key} -> {dest_file}")
            s3.download_file(bucket, key, dest_file)
            found_any = True

    if not found_any:
        logging.warning(f"No objects found at {s3_uri}")


def load_model_and_tokenizer():
    global is_ready, model, tokenizer
    model_uri = os.environ.get("MODEL_URI", "models/v1")
    s3_endpoint = os.environ.get("S3_ENDPOINT", "")

    logging.info(f"Loading model from MODEL_URI={model_uri}, S3_ENDPOINT={s3_endpoint}")

    local_model_path = model_uri
    if model_uri.startswith("s3://"):
        local_cache = os.path.join("/tmp/model_cache", model_version)
        download_s3_prefix(s3_endpoint, model_uri, local_cache)
        local_model_path = local_cache

    if not os.path.exists(local_model_path):
        logging.warning(f"Local model path {local_model_path} does not exist, falling back to base model or local dir")
        if os.path.exists(f"models/{model_version}"):
            local_model_path = f"models/{model_version}"
        else:
            local_model_path = "EleutherAI/pythia-70m"

    logging.info(f"Loading tokenizer & weights from {local_model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(local_model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(local_model_path)
    model.eval()
    is_ready = True
    logging.info(f"Model {model_version} loaded successfully and service is READY.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load model
    load_model_and_tokenizer()
    yield
    # Shutdown


app = FastAPI(lifespan=lifespan)


class ParseRequest(BaseModel):
    text: str


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    if not is_ready:
        return Response(content="Model loading", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return {"status": "ready"}


@app.post("/parse")
def parse(req: ParseRequest, response: Response):
    response.headers["X-Model-Version"] = os.environ.get("MODEL_VERSION", model_version)
    response.headers["X-Served-By"] = pod_name

    if not is_ready or model is None or tokenizer is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "model_not_ready"},
            headers=response.headers
        )

    prompt = f"Command: {req.text}\nJSON:"
    inputs = tokenizer(prompt, return_tensors="pt")

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.eos_token_id,
            do_sample=False
        )

    generated_text = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    if "JSON:" in generated_text:
        raw_output = generated_text.split("JSON:", 1)[1].strip()
    else:
        raw_output = generated_text[len(prompt):].strip()

    # If output contains newline after JSON, cut at first closing brace
    if "}" in raw_output:
        raw_output = raw_output[:raw_output.index("}") + 1]

    is_valid, parsed_data = validate_prediction(raw_output)

    if not is_valid:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "invalid_model_output"},
            headers=response.headers
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=parsed_data,
        headers=response.headers
    )
