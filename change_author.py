#!/usr/bin/env python3
import subprocess
import sys

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode

# Get all commit hashes
stdout, stderr, rc = run("git log --format=%H --reverse")
if rc != 0:
    print("Error getting commits:", stderr)
    sys.exit(1)

commits = stdout.strip().split('\n')
print(f"Found {len(commits)} commits to rewrite")

# Rewrite each commit
for commit_hash in commits:
    # Amend the commit with new author
    cmd = f'git rebase --onto {commit_hash}^ --exec "git commit --amend --no-edit --author=\\'M SRAVANTHI <sravanthim674@gmail.com>\\'" {commit_hash}'
    stdout, stderr, rc = run(cmd)
    if rc != 0:
        print(f"Error on {commit_hash}: {stderr}")
        # Continue anyway
        run("git rebase --abort 2>/dev/null")
    else:
        print(f"Updated {commit_hash[:8]}")

print("Done! Run: git push origin main --force")
