#!/usr/bin/env python3
"""Publishes one month: upserts enriched.json into public/*.ics, copies
the month's work files into archive/<YYYYMM>/, commits public/ +
archive/ + data/glossary.json to main as "Hermes (gaia-menu)", pushes,
and writes <workdir>/published.done.

Usage: publish_month.py <workdir> <YYYYMM>

dinner_rotation.py derives the pairing rotation by replaying
archive/*/enriched.json, so every published month must also be archived.

Refuses to run unless the repo is on branch main. Exit 0 = pushed (or
nothing new to push), 1 = problem (message on stderr).
"""
import shutil
import subprocess, sys
from pathlib import Path

ARCHIVED = ("menu.json", "response.json", "enriched.json")

REPO = Path(__file__).resolve().parent.parent
IDENT = ["-c", "user.name=Hermes (gaia-menu)", "-c", "user.email=hermes-gaia-menu@users.noreply.github.com"]


def git(*a, check=True):
    return subprocess.run(["git", *IDENT, *a], cwd=REPO, text=True, capture_output=True, check=check)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr); return 1
    work, month = Path(sys.argv[1]), sys.argv[2]
    enriched = work / "enriched.json"
    if not enriched.exists():
        print(f"missing {enriched}", file=sys.stderr); return 1
    if git("branch", "--show-current").stdout.strip() != "main":
        print("repo is not on branch main; refusing to publish", file=sys.stderr); return 1
    pull = git("pull", "--rebase", "--autostash", check=False)
    if pull.returncode:
        print("git pull failed:\n" + pull.stderr, file=sys.stderr); return 1
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "publish_ics.py"), str(enriched),
                        "--public-dir", str(REPO / "public")], text=True, capture_output=True)
    if r.returncode:
        print(r.stderr, file=sys.stderr); return 1
    print(r.stderr.strip())

    archive = REPO / "archive" / month
    archive.mkdir(parents=True, exist_ok=True)
    for name in ARCHIVED:
        if (work / name).exists():
            shutil.copy2(work / name, archive / name)
    for pdf in work.glob("*.pdf"):
        shutil.copy2(pdf, archive / pdf.name)

    git("add", "public/", "archive/", "data/glossary.json")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("nothing changed; already up to date")
    else:
        git("commit", "-m", f"Publish {month} menu")
        push = git("push", "origin", "main", check=False)
        if push.returncode:
            print("git push failed:\n" + push.stderr, file=sys.stderr); return 1
        print(f"pushed Publish {month} menu")
    (work / "published.done").write_text("ok\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
