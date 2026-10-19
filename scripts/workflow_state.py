#!/usr/bin/env python3
"""Bounded, opt-in local workflow bookkeeping. Host executes/approves every action."""
import argparse
import copy
import json
from pathlib import PurePosixPath
from execution_state import digest, load, write_new

TERMINAL = {"succeeded", "cancelled", "rolled_back"}

def path_key(path):
    if not isinstance(path, str) or not path or "\\" in path or ":" in path or any(x in path for x in "*?["):
        raise ValueError("ownership needs literal repository-relative paths")
    value = PurePosixPath(path)
    if value.is_absolute() or ".." in value.parts or str(value) == ".":
        raise ValueError("ownership escapes repository")
    return str(value).casefold()

def create(spec):
    allowed = {"mode", "opt_in", "tasks", "max_parallel", "max_events", "event_trigger", "stop_condition"}
    if not isinstance(spec, dict) or set(spec)-allowed:
        raise ValueError("unknown workflow fields")
    mode = spec.get("mode", "single")
    if mode not in ("single", "parallel", "review", "continuous"):
        raise ValueError("unsupported workflow")
    if "opt_in" in spec and type(spec["opt_in"]) is not bool:
        raise ValueError("opt_in must be boolean")
    if mode in ("parallel", "continuous") and spec.get("opt_in") is not True:
        raise ValueError("parallel/continuous work requires explicit opt-in")
    if mode == "continuous" and any(not isinstance(spec.get(k), str) or not spec[k].strip() or len(spec[k]) > 300 for k in ("event_trigger", "stop_condition")):
        raise ValueError("event workflow requires bounded trigger and stop condition")
    maximum, limit = spec.get("max_parallel",1), spec.get("max_events",100)
    if type(maximum) is not int or not 1 <= maximum <= 4 or (mode != "parallel" and maximum != 1):
        raise ValueError("invalid concurrency limit")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("invalid event budget")
    tasks = spec.get("tasks")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 40:
        raise ValueError("workflow needs 1..40 tasks")
    nodes = {}
    ownership = []
    for task in tasks:
        if not isinstance(task, dict) or set(task)-{"id", "owned_files", "depends_on", "max_attempts"}:
            raise ValueError("invalid task fields")
        name = task.get("id")
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or name in nodes:
            raise ValueError("invalid/duplicate task id")
        files, dependencies = task.get("owned_files",[]), task.get("depends_on",[])
        if not isinstance(files,list) or len(files)>40 or (mode=="parallel" and not files):
            raise ValueError("parallel tasks require bounded ownership")
        if not isinstance(dependencies,list) or any(not isinstance(x,str) for x in dependencies) or len(dependencies)>40:
            raise ValueError("invalid dependencies")
        attempts=task.get("max_attempts",1)
        if type(attempts) is not int or not 1 <= attempts <= 5:
            raise ValueError("retry limit must be 1..5 attempts")
        for file in files:
            normalized=path_key(file)
            if mode=="parallel" and any(normalized==old or normalized.startswith(old+"/") or old.startswith(normalized+"/") for old in ownership):
                raise ValueError("conflicting parallel ownership")
            ownership.append(normalized)
        nodes[name]={"owned_files":files,"depends_on":dependencies,"max_attempts":attempts,"attempts":0,"status":"queued"}
    pending=set(nodes)
    resolved=set()
    while pending:
        ready={name for name in pending if set(nodes[name]["depends_on"]) <= resolved}
        if not ready:
            raise ValueError("dependency cycle or missing dependency")
        resolved.update(ready)
        pending-=ready
    body={"schema":1,"kind":"local_workflow_state","spec":spec,"nodes":nodes,"events":[],"stopped":False,"cycles":1,
          "host_execution_required":True,"permissions_granted":False,"writes_allowed":mode!="review"}
    return seal(body)

def seal(body):
    return {**body,"sha256":digest(body)}

def validate(state):
    if not isinstance(state,dict) or state.get("schema")!=1 or state.get("kind")!="local_workflow_state":
        raise ValueError("unsupported state")
    body={k:v for k,v in state.items() if k!="sha256"}
    if state.get("sha256")!=digest(body):
        raise ValueError("state integrity mismatch")
    # Replay the bounded event history, rather than trusting supplied status flags.
    replay=create(state["spec"])
    for event in state["events"]:
        replay=advance(replay,event,verify=False)
    if replay!=state:
        raise ValueError("state does not match its event history")

def ready(state):
    if state["stopped"] or len(state["events"]) >= state["spec"].get("max_events",100):
        return []
    capacity=state["spec"].get("max_parallel",1)-sum(n["status"]=="running" for n in state["nodes"].values())
    return [name for name,n in state["nodes"].items()
            if n["status"] in ("queued","failed","interrupted") and n["attempts"]<n["max_attempts"]
            and all(state["nodes"][d]["status"]=="succeeded" for d in n["depends_on"])][:max(0,capacity)]

def advance(state,event,verify=True):
    if verify:
        validate(state)
    if not isinstance(event,dict) or set(event)-{"id","kind","task","receipt_sha256","trigger"}:
        raise ValueError("invalid event fields")
    if not isinstance(event.get("id"),str) or not 1<=len(event["id"])<=100:
        raise ValueError("bounded event id required")
    for old in state["events"]:
        if old["id"]==event["id"]:
            if old!=event:
                raise ValueError("duplicate event id has conflicting content")
            return state
    kind=event.get("kind")
    limit=state["spec"].get("max_events",100)
    # A work budget must still permit bounded host cleanup and rollback receipts.
    cleanup=kind in ("stop","cancel","succeed","fail","interrupt","rollback")
    if (state["stopped"] and kind!="rollback") or (len(state["events"])>=limit and not cleanup):
        raise ValueError("workflow stopped or event budget exhausted")
    if len(state["events"])>=limit+3*len(state["nodes"])+1:
        raise ValueError("cleanup event reserve exhausted")
    body=copy.deepcopy({k:v for k,v in state.items() if k!="sha256"})
    if kind=="stop":
        body["stopped"]=True
        for node in body["nodes"].values():
            if node["status"] not in TERMINAL:
                node["status"]="cancelled"
    elif kind=="cycle":
        if state["spec"].get("mode")!="continuous" or event.get("trigger")!=state["spec"]["event_trigger"]:
            raise ValueError("a new cycle requires the declared continuous trigger")
        if not all(n["status"]=="succeeded" for n in body["nodes"].values()):
            raise ValueError("finish the current cycle before starting another")
        body["cycles"]+=1
        for node in body["nodes"].values():
            node["status"]="queued"
            node["attempts"]=0
    elif kind in ("start","succeed","fail","interrupt","cancel","rollback"):
        name=event.get("task")
        if not isinstance(name,str) or name not in body["nodes"]:
            raise ValueError("event requires an existing task")
        node=body["nodes"][name]
        if kind=="start":
            if name not in ready(state):
                raise ValueError("dependencies, ownership, concurrency or retry budget prevent start")
            if state["spec"].get("mode")=="continuous" and event.get("trigger")!=state["spec"]["event_trigger"]:
                raise ValueError("continuous start requires its explicit trigger")
            node["attempts"]+=1
            node["status"]="running"
        elif kind in ("succeed","rollback"):
            receipt=event.get("receipt_sha256")
            if not isinstance(receipt,str) or len(receipt)!=64 or any(c not in "0123456789abcdef" for c in receipt):
                raise ValueError("success/rollback needs an explicit host receipt hash")
            if kind=="succeed" and node["status"]!="running":
                raise ValueError("only running work can succeed")
            if kind=="rollback" and node["status"] not in ("failed","interrupted","cancelled","succeeded"):
                raise ValueError("rollback requires stopped or completed work")
            node["status"]="succeeded" if kind=="succeed" else "rolled_back"
            if kind=="rollback":
                affected={name}
                while True:
                    dependants={k for k,n in body["nodes"].items() if set(n["depends_on"])&affected}
                    if dependants<=affected:
                        break
                    affected|=dependants
                for key in affected-{name}:
                    body["nodes"][key]["status"]="cancelled"
        else:
            if kind in ("fail","interrupt") and node["status"]!="running":
                raise ValueError("only running work can fail or interrupt")
            if kind=="cancel" and node["status"] in TERMINAL:
                raise ValueError("terminal work cannot be cancelled")
            node["status"]={"fail":"failed","interrupt":"interrupted","cancel":"cancelled"}[kind]
    else:
        raise ValueError("unsupported lifecycle event")
    body["events"].append(event)
    return seal(body)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for mode in ("create","advance","ready"):
        p=sub.add_parser(mode)
        p.add_argument("input")
        if mode=="advance": p.add_argument("event")
        if mode!="ready": p.add_argument("--output",required=True)
    args=parser.parse_args()
    try:
        value=load(args.input)
        if args.command=="create": result=create(value)
        else:
            validate(value)
            if args.command=="ready":
                print(json.dumps({"ready":ready(value),"host_execution_required":True}))
                return
            result=advance(value,load(args.event))
        write_new(args.output,result)
        print(json.dumps({"written":True,"sha256":result["sha256"]}))
    except (ValueError,OSError,KeyError,TypeError) as exc:
        parser.error(str(exc))

if __name__=="__main__": main()
