"""Drive one MiroShark run from the RAWRS launch brief; log every step to stdout.

usage: miroshark_run.py [max_rounds] [sim_id_to_resume or ""] [seed.md]   (run inside the MiroShark Codespace)
"""
import json, sys, time
import requests

B = "http://localhost:5001/api"
SEED = sys.argv[3] if len(sys.argv) > 3 else "/workspaces/rawrs_seed.md"
MAX_ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
RESUME = sys.argv[2] if len(sys.argv) > 2 else None
DONE = {"completed", "ready", "success", "finished", "stopped"}
BAD = {"failed", "error"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def ok(r):
    j = r.json()
    if not j.get("success", False):
        log("FAIL", r.status_code, json.dumps(j)[:800])
        sys.exit(1)
    return j["data"]


def wait(fetch, label, every=15, limit=7200):
    t0 = time.time()
    while time.time() - t0 < limit:
        d = fetch()
        s = str(d.get("status") or d.get("runner_status") or "").lower()
        log(label, s, d.get("progress"), str(d.get("message") or "")[:120],
            d.get("current_round"), d.get("total_rounds"), d.get("total_actions_count"))
        if s in DONE:
            return d
        if s in BAD:
            log("FAIL", json.dumps(d)[:800])
            sys.exit(1)
        time.sleep(every)
    log("TIMEOUT", label)
    sys.exit(1)


def prepare():
    req = open(SEED).read().split("## The question", 1)[1].strip()
    with open(SEED, "rb") as f:
        d = ok(requests.post(f"{B}/graph/ontology/generate",
                             files={"files": ("rawrs_seed.md", f, "text/markdown")},
                             data={"simulation_requirement": req, "project_name": "RAWRS launch"}, timeout=900))
    pid = d["project_id"]
    log("project", pid, [e.get("name") for e in d["ontology"].get("entity_types", [])])
    d = ok(requests.post(f"{B}/graph/build", json={"project_id": pid}, timeout=120))
    wait(lambda: ok(requests.get(f"{B}/graph/task/{d['task_id']}", timeout=60)), "graph")
    d = ok(requests.post(f"{B}/simulation/create", json={"project_id": pid, "enable_twitter": True,
                                                         "enable_reddit": True, "country": "us"}, timeout=120))
    sid = d["simulation_id"]
    log("simulation", sid)
    d = ok(requests.post(f"{B}/simulation/prepare", json={"simulation_id": sid, "parallel_profile_count": 3},
                         timeout=120))
    if not d.get("already_prepared"):
        tid = d["task_id"]
        wait(lambda: ok(requests.post(f"{B}/simulation/prepare/status",
                                      json={"task_id": tid, "simulation_id": sid}, timeout=60)), "prepare")
    return sid


sid = RESUME or prepare()
ok(requests.post(f"{B}/simulation/start", json={"simulation_id": sid, "platform": "parallel",
                                                "max_rounds": MAX_ROUNDS, "force": bool(RESUME)}, timeout=120))
wait(lambda: ok(requests.get(f"{B}/simulation/{sid}/run-status", timeout=60)), "run", every=30)
d = ok(requests.post(f"{B}/report/generate", json={"simulation_id": sid}, timeout=120))
tid = d.get("task_id")
wait(lambda: ok(requests.post(f"{B}/report/generate/status", json={"task_id": tid, "simulation_id": sid},
                              timeout=60)), "report", every=30)
log("DONE", sid)
