"""End-to-end smoke test against a running backend: python scripts/smoke.py [live|fixture]"""
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api"
mode = sys.argv[1] if len(sys.argv) > 1 else "live"
c = httpx.Client(base_url=BASE, timeout=60)

print("health", c.get("/health").json())
skills = c.get("/skills").json()
print("skills", len(skills["skills"]), list(skills["stage_bindings"]))
brief = c.get("/templates/demo").json()
study = c.post("/studies", json={"brief": brief, "mode": mode}).json()
sid = study["id"]
print("created", sid)


def wait(until, label):
    seen = 0
    t0 = time.time()
    while True:
        s = c.get(f"/studies/{sid}").json()
        for ev in s["timeline"][seen:]:
            print(f"  [{ev['stage']}] {ev['level']}: {ev['message']}")
        seen = len(s["timeline"])
        if s["status"] in until:
            print(label, "->", s["status"], f"{time.time() - t0:.0f}s", s.get("error") or "")
            return s
        if time.time() - t0 > 600:
            raise SystemExit("timeout")
        time.sleep(3)


c.post(f"/studies/{sid}/plan")
s = wait({"AWAITING_CONFIRMATION", "FAILED"}, "plan")
if s["status"] == "FAILED":
    raise SystemExit(1)
for seeds in s["plan"]["concept_seeds"]:
    print(seeds["concept_id"], "entities", [e["name"] for e in seeds["entity_candidates"] if e["selected"]],
          "tags", [t["name"] for t in seeds["tag_candidates"] if t["selected"]], "ambiguous", seeds["ambiguous"])
r = c.post(f"/studies/{sid}/run")
print("run", r.status_code)
s = wait({"COMPLETE", "FAILED"}, "run")
print("evidence", [(e["id"], e["output_type"].split(":")[-1], e["market"], e["status"], len(e["items"])) for e in s["evidence"]])
print("summary:", s["executive_summary"])
print("experiments:", [e["title"] for e in s["experiments"]])
print("skills used:", [(u["stage"], u["skill"]) for u in s["skills_used"]])
print("baseline:", bool(s["baseline"]), "report chars:", len(s["report_markdown"]))
