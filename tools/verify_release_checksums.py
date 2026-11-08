import os
import shutil
import subprocess
import sys
import tempfile
import hashlib

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
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Downloading release v1.0.0 assets to {tmpdir}...")
        res = subprocess.run([gh_bin, "release", "download", "v1.0.0", "--dir", tmpdir], env=env, capture_output=True, text=True)
        if res.returncode != 0:
            print("Download failed:", res.stderr)
            sys.exit(1)

        downloaded_files = sorted(os.listdir(tmpdir))
        print("Downloaded files:", downloaded_files)

        # Compare with models/v1/model.sha256
        expected_sha = {}
        with open("models/v1/model.sha256", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2:
                    expected_sha[parts[1]] = parts[0]

        all_matched = True
        for fname, exp_hash in expected_sha.items():
            fpath = os.path.join(tmpdir, fname)
            if not os.path.exists(fpath):
                print(f"FAIL: {fname} missing in downloaded release")
                all_matched = False
                continue
            
            h = hashlib.sha256()
            with open(fpath, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            actual_hash = h.hexdigest()
            if actual_hash == exp_hash:
                print(f"PASS: {fname} checksum matches ({actual_hash})")
            else:
                print(f"FAIL: {fname} mismatch! Exp: {exp_hash}, Got: {actual_hash}")
                all_matched = False

        if all_matched:
            print("\n>>> ALL RELEASE ASSET CHECKSUMS MATCH models/v1/model.sha256 100%! <<<")

if __name__ == "__main__":
    main()

