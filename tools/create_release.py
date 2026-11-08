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
    if not token:
        print("ERROR: Could not get GitHub token from git credentials")
        sys.exit(1)
    
    gh_bin = shutil.which("gh")
    if not gh_bin:
        print("ERROR: gh CLI not found on PATH")
        sys.exit(1)

    env = os.environ.copy()
    env['GH_TOKEN'] = token

    files_to_upload = [
        "models/v1/config.json",
        "models/v1/generation_config.json",
        "models/v1/model.safetensors",
        "models/v1/tokenizer.json",
        "models/v1/tokenizer_config.json",
        "models/v1/model.sha256"
    ]

    for f in files_to_upload:
        if not os.path.exists(f):
            print(f"ERROR: File not found: {f}")
            sys.exit(1)

    print(f"Using gh binary: {gh_bin}")
    print("Creating release v1.0.0 on GitHub...")
    check_cmd = [gh_bin, "release", "view", "v1.0.0"]
    r = subprocess.run(check_cmd, env=env, capture_output=True, text=True)
    if r.returncode == 0:
        print("Release v1.0.0 already exists, uploading/overwriting assets...")
        upload_cmd = [gh_bin, "release", "upload", "v1.0.0"] + files_to_upload + ["--clobber"]
        res = subprocess.run(upload_cmd, env=env, capture_output=True, text=True)
        print("Upload result:", res.returncode)
        print(res.stdout, res.stderr)
    else:
        create_cmd = [gh_bin, "release", "create", "v1.0.0"] + files_to_upload + ["-t", "v1.0.0", "-n", "Distilled Pythia-70M Student Model v1.0.0 for Command Parsing"]
        res = subprocess.run(create_cmd, env=env, capture_output=True, text=True)
        print("Create release result:", res.returncode)
        print(res.stdout, res.stderr)

if __name__ == '__main__':
    main()
