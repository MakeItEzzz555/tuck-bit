#!/usr/bin/env python3
"""Zero-model-token local skill smoke tests, optional upstream skills CLI interoperability."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/"skills"/"tuck-bit"/"SKILL.md"

def frontmatter_name(content):
    if not content.startswith("---\n"):
        return None
    for line in content.split("---",2)[1].splitlines():
        if line.strip().startswith("name:"):
            return line.partition(":")[2].strip().strip(chr(39)+chr(34))
    return None

def run(command, cwd=None, env=None, timeout=90):
    proc=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout)
    if proc.returncode!=0:
        raise RuntimeError(f"{command[0]} failed: {(proc.stdout+proc.stderr)[-1100:]}")
    return proc.stdout+proc.stderr

def offline():
    assert frontmatter_name(SKILL.read_text(encoding="utf-8"))=="tuck-bit"
    metadata=json.loads((ROOT/"distribution.json").read_text(encoding="utf-8"))
    assert metadata["name"]=="tuck-bit"
    import importlib.util
    spec=importlib.util.spec_from_file_location("free_smoke_installer",ROOT/"scripts"/"install.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="tuckbit-offline-") as folder:
        root=Path(folder)
        for client in module.CLIENTS:
            module.install(root,"project",client)
            assert module.digest(root/module.PROJECT[client])==module.digest(module.SOURCE)
            module.uninstall(root,"project",client)
            assert not (root/module.PROJECT[client]).exists()
    print("PASS: offline six-client install/uninstall and skill metadata (no model)")

def interop():
    if not shutil.which("npx"):
        print("SKIP: npx unavailable")
        return
    with tempfile.TemporaryDirectory(prefix="tuckbit-interop-") as folder:
        root=Path(folder)
        home=root/"home";home.mkdir()
        project=root/"project";project.mkdir()
        env=os.environ.copy()
        env["HOME"]=str(home)
        env["XDG_CONFIG_HOME"]=str(home/".config")
        npm_cache=Path.home()/".npm"
        if npm_cache.is_dir():
            env["npm_config_cache"]=str(npm_cache)
        command=["npx","--yes","skills","add",str(ROOT),"--skill","tuck-bit",
                 "--agent","codex","-y","--copy"]
        run(command,cwd=project,env=env)
        installed=project/".agents/skills/tuck-bit/SKILL.md"
        assert installed.is_file()
        assert frontmatter_name(installed.read_text(encoding="utf-8"))=="tuck-bit"
        print("PASS: upstream skills CLI installed TuckBit into isolated Codex project")
        output=run(["npx","--yes","skills","use",str(ROOT),"--skill","tuck-bit"],cwd=project,env=env)
        assert "<SKILL.md>" in output and "TuckBit" in output
        print("PASS: upstream skills CLI rendered prompt without launching an AI agent")

def claude_check():
    if not shutil.which("claude"):
        print("SKIP: Claude CLI unavailable")
        return
    run(["claude","plugin","validate",str(ROOT),"--strict"],cwd=ROOT,timeout=45)
    print("PASS: Claude Code plugin strict validation (no model)")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--interop",action="store_true")
    p.add_argument("--claude-validator",action="store_true")
    args=p.parse_args()
    try:
        offline()
        if args.interop: interop()
        if args.claude_validator: claude_check()
        return 0
    except (AssertionError,RuntimeError,subprocess.TimeoutExpired,OSError,ValueError) as e:
        print(f"FAIL: {e}",file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
