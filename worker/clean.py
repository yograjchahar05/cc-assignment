"""Clean teacher shard outputs according to strict project specifications.

Filter rules:
  (a) replies that are not valid JSON
  (b) replies whose keys are not exactly intent, date, time, and place
  (c) replies whose intent is not one of the eight
  (d) replies with a slot value that is neither null nor text that appears in the command
  (e) duplicate commands (keep the one with the smallest id)

Outputs:
  datasets/v1/train.jsonl: Cleaned records sorted by id
  datasets/v1/train.sha256: SHA-256 checksum of train.jsonl
  datasets/v1/clean_stats.json: Summary table with counts
"""
import glob
import hashlib
import json
import os
import sys

VALID_INTENTS = {
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events",
}

EXPECTED_KEYS = {"intent", "date", "time", "place"}


def compute_sha256(filepath):
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def clean_shards(shard_dir="datasets/teacher", output_file="datasets/v1/train.jsonl", sha_file="datasets/v1/train.sha256", stats_file="datasets/v1/clean_stats.json"):
    shard_pattern = os.path.join(shard_dir, "shard-*.jsonl")
    shard_files = sorted(glob.glob(shard_pattern))

    if not shard_files:
        sys.exit(f"No shard files found matching: {shard_pattern}")

    print(f"Found {len(shard_files)} shard file(s): {shard_files}")

    all_records = []
    seen_ids = set()
    duplicate_ids = []

    for sfile in shard_files:
        with open(sfile, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    print(f"Warning: malformed record JSON at {sfile}:{line_no}")
                    continue

                rec_id = record.get("id")
                if rec_id in seen_ids:
                    duplicate_ids.append(rec_id)
                seen_ids.add(rec_id)
                all_records.append(record)

    input_count = len(all_records)
    print(f"Total input records across all shards: {input_count}")
    if duplicate_ids:
        print(f"Warning: Found {len(duplicate_ids)} duplicate IDs across shards: {duplicate_ids[:5]}...")

    # Sort all records by id order
    all_records.sort(key=lambda r: r.get("id", ""))

    rejected_a = 0  # not valid JSON
    rejected_b = 0  # keys not exactly intent, date, time, place
    rejected_c = 0  # intent not one of the eight
    rejected_d = 0  # slot not null and not appearing in command text
    rejected_e = 0  # duplicate commands (keep one with smallest id)
    kept_records = []

    seen_command_texts = {}  # text -> smallest id

    for record in all_records:
        rec_id = record.get("id")
        cmd_text = record.get("text", "")
        raw = record.get("teacher_raw", "")

        # (a) Is teacher_raw valid JSON?
        try:
            parsed = json.loads(str(raw).strip())
        except (json.JSONDecodeError, TypeError):
            rejected_a += 1
            continue

        # (b) Are keys exactly intent, date, time, place?
        if not isinstance(parsed, dict) or set(parsed.keys()) != EXPECTED_KEYS:
            rejected_b += 1
            continue

        # (c) Is intent one of the eight?
        intent = parsed.get("intent")
        if intent not in VALID_INTENTS:
            rejected_c += 1
            continue

        # (d) Slot values: must be null or substring appearing in command text
        slot_valid = True
        norm_cmd = " ".join(cmd_text.lower().split())
        for slot in ("date", "time", "place"):
            val = parsed.get(slot)
            if val is not None:
                if not isinstance(val, str):
                    slot_valid = False
                    break
                norm_val = " ".join(val.lower().split())
                if norm_val not in norm_cmd:
                    slot_valid = False
                    break

        if not slot_valid:
            rejected_d += 1
            continue

        # (e) Duplicate command text: keep smallest id
        # Normalize command text for duplicate detection
        if norm_cmd in seen_command_texts:
            rejected_e += 1
            continue
        seen_command_texts[norm_cmd] = rec_id

        kept_records.append(record)

    kept_count = len(kept_records)

    # Verification: input = (a) + (b) + (c) + (d) + duplicates + kept
    total_accounted = rejected_a + rejected_b + rejected_c + rejected_d + rejected_e + kept_count
    assert total_accounted == input_count, f"Math check failed: {total_accounted} != {input_count}"

    # Write datasets/v1/train.jsonl
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as out:
        for r in kept_records:
            out.write(json.dumps(r) + "\n")

    # Compute SHA-256
    checksum = compute_sha256(output_file)
    with open(sha_file, "w", encoding="utf-8") as f_sha:
        f_sha.write(checksum + "  train.jsonl\n")

    stats = {
        "input_records": input_count,
        "rejected_a_invalid_json": rejected_a,
        "rejected_b_invalid_keys": rejected_b,
        "rejected_c_invalid_intent": rejected_c,
        "rejected_d_invalid_slots": rejected_d,
        "rejected_e_duplicates": rejected_e,
        "records_kept": kept_count,
        "checksum_sha256": checksum,
    }

    if stats_file:
        os.makedirs(os.path.dirname(stats_file), exist_ok=True)
        with open(stats_file, "w", encoding="utf-8") as sf:
            json.dump(stats, sf, indent=2)

    print("\n--- Cleaning Summary Table ---")
    print(f"Input records:               {input_count}")
    print(f"Rejected (a) Invalid JSON:   {rejected_a}")
    print(f"Rejected (b) Invalid Keys:   {rejected_b}")
    print(f"Rejected (c) Invalid Intent: {rejected_c}")
    print(f"Rejected (d) Invalid Slots:  {rejected_d}")
    print(f"Rejected (e) Duplicates:     {rejected_e}")
    print(f"Records Kept:                {kept_count}")
    print(f"Verification: {input_count} = {rejected_a} + {rejected_b} + {rejected_c} + {rejected_d} + {rejected_e} + {kept_count} (PASS)")
    print(f"SHA-256: {checksum}")
    return stats


if __name__ == "__main__":
    clean_shards()

