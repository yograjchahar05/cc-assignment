"""Sequence-Level Knowledge Distillation training script for EleutherAI/pythia-70m.

Reads training configuration exclusively from training/config.yaml.
Supports optional --subset N (or SUBSET=N env var) to train on the first N examples.
Saves epoch training losses to training/loss.csv.
Saves fine-tuned model, tokenizer, and computes SHA-256 checksum in output directory.
"""
import argparse
import csv
import hashlib
import json
import logging
import os
import random
import sys
import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

# Unbuffered logging for real-time visibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", force=True)


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class DistillationDataset(Dataset):
    def __init__(self, records, tokenizer, max_seq_length=64):
        self.examples = []
        for r in records:
            cmd = r.get("text", "")
            raw = r.get("teacher_raw")
            if isinstance(raw, dict):
                raw_json = json.dumps(raw)
            else:
                raw_json = str(raw).strip()

            prompt_text = f"Command: {cmd}\nJSON: "
            target_text = f"{raw_json}{tokenizer.eos_token}"

            prompt_ids = tokenizer.encode(prompt_text, add_special_tokens=True)
            target_ids = tokenizer.encode(target_text, add_special_tokens=False)

            ids = prompt_ids + target_ids
            labels = [-100] * len(prompt_ids) + target_ids

            if len(ids) > max_seq_length:
                ids = ids[:max_seq_length]
                labels = labels[:max_seq_length]

            self.examples.append({
                "input_ids": ids,
                "labels": labels
            })

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        return self.examples[idx]


def collate_fn(batch, pad_token_id=0):
    """Dynamic padding to max length in the batch."""
    max_len = max(len(item["input_ids"]) for item in batch)
    input_ids_list = []
    attention_mask_list = []
    labels_list = []

    for item in batch:
        cur_len = len(item["input_ids"])
        pad_len = max_len - cur_len

        input_ids = item["input_ids"] + [pad_token_id] * pad_len
        attention_mask = [1] * cur_len + [0] * pad_len
        labels = item["labels"] + [-100] * pad_len

        input_ids_list.append(input_ids)
        attention_mask_list.append(attention_mask)
        labels_list.append(labels)

    return {
        "input_ids": torch.tensor(input_ids_list, dtype=torch.long),
        "attention_mask": torch.tensor(attention_mask_list, dtype=torch.long),
        "labels": torch.tensor(labels_list, dtype=torch.long)
    }


def compute_dir_sha256(directory, output_file):
    """Compute sha256 checksums of all files in directory and write to output_file."""
    sha_lines = []
    for root, _, files in sorted(os.walk(directory)):
        for fname in sorted(files):
            if fname.endswith(".sha256"):
                continue
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, directory)
            h = hashlib.sha256()
            with open(fpath, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            sha_lines.append(f"{h.hexdigest()}  {rel_path}\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(sha_lines)

    logging.info(f"Saved SHA-256 checksums to {output_file}")


def main():
    # Set PyTorch thread count to physical cores to maximize cache locality
    threads = min(os.cpu_count() or 4, 4)
    torch.set_num_threads(threads)

    parser = argparse.ArgumentParser(description="Train Pythia-70M student via sequence KD")
    parser.add_argument("--config", default="training/config.yaml", help="Path to training config.yaml")
    parser.add_argument("--subset", type=int, default=None, help="Train on first N examples (e.g. 50)")
    parser.add_argument("--output_dir", default=None, help="Override output directory")
    parser.add_argument("--epochs", type=int, default=None, help="Override number of epochs")
    parser.add_argument("--seed", type=int, default=None, help="Override random seed")
    args = parser.parse_args()

    # Read config.yaml
    if not os.path.exists(args.config):
        sys.exit(f"Config file not found: {args.config}")
    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Resolve settings (env vars and CLI args take precedence if provided)
    subset_env = os.environ.get("SUBSET")
    subset = args.subset if args.subset is not None else (int(subset_env) if subset_env else None)
    output_dir = args.output_dir or os.environ.get("OUTPUT_DIR") or config.get("output_dir", "models/v1")
    seed = args.seed if args.seed is not None else (int(os.environ.get("SEED")) if os.environ.get("SEED") else config.get("seed", 42))
    num_epochs = args.epochs if args.epochs is not None else (int(os.environ.get("EPOCHS")) if os.environ.get("EPOCHS") else config.get("num_epochs", 3))
    batch_size = config.get("batch_size", 8)
    learning_rate = float(config.get("learning_rate", 5.0e-5))
    max_seq_length = config.get("max_seq_length", 64)
    model_name = config.get("model_name_or_path", "EleutherAI/pythia-70m")
    train_path = config.get("train_data_path", "datasets/v1/train.jsonl")

    set_seed(seed)
    logging.info(f"Training settings: seed={seed}, epochs={num_epochs}, batch_size={batch_size}, lr={learning_rate}, subset={subset}, output_dir={output_dir}")

    # Load training data
    if not os.path.exists(train_path):
        sys.exit(f"Training data not found: {train_path}")

    records = []
    with open(train_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    # Task specification: "Use no more than 1,500 training examples: the first 1,500 records in the cleaned dataset."
    records = records[:1500]
    if subset:
        records = records[:subset]
        logging.info(f"Using SUBSET={subset} records for training")
    else:
        logging.info(f"Using {len(records)} records for training (capped at 1,500)")

    # Load tokenizer and model in float32 for CPU stability
    logging.info(f"Loading model and tokenizer: {model_name} (dtype=float32)")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.float32)
    model.train()

    dataset = DistillationDataset(records, tokenizer, max_seq_length=max_seq_length)
    pad_id = tokenizer.pad_token_id or 0
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, collate_fn=lambda b: collate_fn(b, pad_id))

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    total_steps = len(dataloader) * num_epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=int(0.1 * total_steps), num_training_steps=total_steps)

    os.makedirs(output_dir, exist_ok=True)
    loss_csv_path = "training/loss.csv"
    os.makedirs("training", exist_ok=True)

    loss_records = []
    logging.info(f"Starting training loop on CPU ({len(dataloader)} batches/epoch, total steps={total_steps})...")
    for epoch in range(1, num_epochs + 1):
        epoch_loss = 0.0
        steps = 0
        for step, batch in enumerate(dataloader, 1):
            optimizer.zero_grad()
            input_ids = batch["input_ids"]
            attention_mask = batch["attention_mask"]
            labels = batch["labels"]

            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            scheduler.step()

            epoch_loss += loss.item()
            steps += 1

            if step % 10 == 0 or step == len(dataloader):
                logging.info(f"Epoch {epoch}/{num_epochs} | Step {step}/{len(dataloader)} | Batch Loss: {loss.item():.4f}")

        avg_loss = epoch_loss / max(steps, 1)
        loss_records.append({"epoch": epoch, "loss": round(avg_loss, 4)})
        logging.info(f"--> Epoch {epoch} complete | Average Loss: {avg_loss:.4f}")

    # Save training/loss.csv
    with open(loss_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["epoch", "loss"])
        writer.writeheader()
        writer.writerows(loss_records)
    logging.info(f"Saved loss history to {loss_csv_path}")

    # Save model and tokenizer
    logging.info(f"Saving fine-tuned model and tokenizer to {output_dir}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Compute checksum
    sha256_path = os.path.join(output_dir, "model.sha256")
    compute_dir_sha256(output_dir, sha256_path)

    logging.info("Training and export complete!")


if __name__ == "__main__":
    main()
