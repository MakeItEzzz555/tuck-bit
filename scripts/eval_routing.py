#!/usr/bin/env python3
"""Deterministic policy regression suite. This is NOT a model token-savings benchmark."""
import json
from pathlib import Path
from workflow_router import route

ROOT = Path(__file__).resolve().parents[1]

def run_cases(path=ROOT/"evals/routing-cases.json"):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise ValueError("Unsupported case format")
    results=[]
    ids=set()
    for item in data["cases"]:
        case_id=item["id"]
        if case_id in ids:
            raise ValueError("Duplicate case id")
        ids.add(case_id)
        output=route(item["task"])
        actual={
            "depth":output["routing"]["depth"],
            "workflow":output["routing"]["workflow"]
        }
        expected=item["expect"]
        checks_preserved=all(
            check in output["routing"]["checks"]
            for check in item["task"].get("checks",[])
        )
        constraints_preserved=(
            output["task"]["constraints_verbatim"]==item["task"].get("constraints",[])
        )
        success=actual==expected and checks_preserved and constraints_preserved
        results.append({"case":case_id,"pass":success,"expected":expected,"actual":actual,
                        "checks_preserved":checks_preserved,"constraints_preserved":constraints_preserved})
    return results

def main():
    results=run_cases()
    for case in results:
        print(("[PASS] " if case["pass"] else "[FAIL] ")+case["case"])
    passed=sum(x["pass"] for x in results)
    print(f"Routing policy evaluation: {passed}/{len(results)} passed (deterministic; no model)")
    raise SystemExit(0 if passed==len(results) else 1)

if __name__=="__main__":
    main()
