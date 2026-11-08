import json
import os
import shutil
import subprocess
import sys

def get_git_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    for line in out.splitlines():
        if line.startswith('password='):
            return line.split('=', 1)[1]
    return os.environ.get('GH_TOKEN', '')

def main():
    token = get_git_token()
    env = os.environ.copy()
    if token:
        env['GH_TOKEN'] = token

    gh_bin = shutil.which("gh")
    r = subprocess.run([gh_bin, 'release', 'view', 'v1.0.0', '--json', 'assets'], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print("Failed to view release:", r.stderr)
        sys.exit(1)

    assets = json.loads(r.stdout).get("assets", [])
    expected = {}
    with open("models/v1/model.sha256", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 2:
                expected[parts[1]] = parts[0]

    print("=== GitHub Release v1.0.0 Asset SHA-256 Verification ===")
    all_ok = True
    for a in assets:
        name = a["name"]
        digest = a.get("digest", "")
        if digest.startswith("sha256:"):
            gh_sha = digest.split("sha256:")[1]
        else:
            gh_sha = digest

        if name in expected:
            exp_sha = expected[name]
            match = (gh_sha == exp_sha)
            status = "MATCH [PASS]" if match else "MISMATCH [FAIL]"
            print(f"File: {name:<24} Size: {a['size']:<10} SHA-256: {gh_sha[:16]}... {status}")
            if not match:
                all_ok = False

    if all_ok:
        print("\nAll model release assets verified matching models/v1/model.sha256!")
    else:
        print("\nSome checksums mismatched!")

if __name__ == "__main__":
    main()

