#!/usr/bin/env python3
"""Generate provider manifests from distribution.json. No network or agent calls."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def manifests(data):
    name=data["name"]
    version=data["version"]
    desc=data["description"]
    publisher=data["publisher"]
    repo=data["repository"]
    market=data["marketplace_name"]
    return {
        "plugin.json": {
            "$schema":"https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name":name,"version":version,"description":desc,
            "author":{"name":publisher},"repository":repo,"license":"MIT",
            "keywords":["agent-skills","context-efficiency","tool-discovery","agentic-coding"]
        },
        ".claude-plugin/plugin.json":{
            "name":name,"version":version,"description":desc,
            "author":{"name":publisher},"license":"MIT"
        },
        ".claude-plugin/marketplace.json":{
            "name":market,
            "description":"Private TuckBit development plugin catalog; opt-in only.",
            "owner":{"name":publisher},
            "plugins":[{"name":name,"description":desc,
                        "source":{"source":"github","repo":publisher+"/"+name}}]
        },
        ".codex-plugin/plugin.json":{
            "name":name,"version":version,"description":desc,
            "author":{"name":publisher},"skills":"./skills/"
        },
        ".agents/plugins/marketplace.json":{
            "name":market,
            "interface":{"displayName":"TuckBit Preview"},
            "plugins":[{
                "name":name,
                "source":{"source":"local","path":"./"},
                "policy":{"installation":"AVAILABLE","authentication":"ON_INSTALL"},
                "category":"Productivity"
            }]
        },
        "gemini-extension.json":{
            "name":name,"version":version,"description":desc
        }
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true",help="verify generated files without modification")
    args=parser.parse_args()
    data=json.loads((ROOT/"distribution.json").read_text(encoding="utf-8"))
    expected=manifests(data)
    bad=[]
    for rel,obj in expected.items():
        path=ROOT/rel
        text=json.dumps(obj,indent=2,ensure_ascii=False)+"\n"
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8")!=text:
                bad.append(rel)
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding="utf-8")
    skill=ROOT/"skills"/data["name"]/"SKILL.md"
    if not skill.is_file():
        bad.append("SKILL.md")
    elif f'  version: "{data["version"]}"' not in skill.read_text(encoding="utf-8"):
        bad.append("SKILL.md metadata version")
    if bad:
        print("FAIL: "+", ".join(bad),file=sys.stderr)
        return 1
    print(("Verified" if args.check else "Generated")+" "+str(len(expected))+" distribution manifests")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
