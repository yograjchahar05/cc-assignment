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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class DistillationDataset(Dataset):
    def __init__(self, records, tokenizer, max_seq_length=128):
        self.examples = []
        for r in records:
            cmd = r.get("text", "")
            # teacher_raw can be a JSON string or already parsed dict
            raw = r.get("teacher_raw")
            if isinstance(raw, dict):
                raw_json = json.dumps(raw)
            else:
                raw_json = str(raw).strip()

            prompt_text = f"Command: {cmd}\nJSON:"
            full_text = f"{prompt_text} {raw_json}"

            prompt_enc = tokenizer(prompt_text, add_special_tokens=True)
            prompt_len = len(prompt_enc["input_ids"])

            full_enc = tokenizer(
                full_text,
                truncation=True,
                max_length=max_seq_length,
                padding="max_length",
                return_tensors="pt"
            )

            input_ids = full_enc["input_ids"].squeeze(0)
            attention_mask = full_enc["attention_mask"].squeeze(0)

            # Mask out the prompt tokens in labels so loss is only computed on the JSON target
            labels = input_ids.clone()
            labels[:prompt_len] = -100
            # Also ignore padding tokens in loss calculation
            labels[attention_mask == 0] = -100

            self.examples.append({
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "labels": labels
            })

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        return self.examples[idx]


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
    parser = argparse.ArgumentParser(description="Fine-tune pythia-70m with sequence-level KD.")
    parser.add_argument("--config", default="training/config.yaml", help="Path to configuration yaml")
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
    max_seq_length = config.get("max_seq_length", 128)
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

    # Load tokenizer and model
    logging.info(f"Loading model and tokenizer: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_name)
    model.train()

    dataset = DistillationDataset(records, tokenizer, max_seq_length=max_seq_length)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    total_steps = len(dataloader) * num_epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=int(0.1 * total_steps), num_training_steps=total_steps)

    os.makedirs(output_dir, exist_ok=True)
    loss_csv_path = "training/loss.csv"
    os.makedirs("training", exist_ok=True)

    loss_records = []
    logging.info("Starting training loop on CPU...")
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

            if step % 25 == 0 or step == len(dataloader):
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
