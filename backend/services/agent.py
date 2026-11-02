"""Autopilot: seven agents run as a LangGraph workflow. If LangGraph is not installed, the same steps run one after another.

Planner > Job Scout > Matcher > Cover Letter Writer > Outreach Agent > Interview Coach > Approval Gate
The agents only search, score and DRAFT. Nothing is sent: every draft waits for the user's approval.
"""
import operator
from typing import Annotated, TypedDict

from services import search, store, writer
from services.interview import generate

STEPS = ["Planner", "Job Scout", "Matcher", "Cover Letter Writer", "Outreach Agent", "Interview Coach", "Approval Gate"]


def _step(agent: str, message: str, status: str = "done") -> list[dict]:
    return [{"agent": agent, "status": status, "message": message}]


def planner(state: dict) -> dict:
    profile = store.profile_data(state["user_id"])
    if not profile:
        return {"stop": True, "trace": _step("Planner", "No resume found. Upload your resume on the Profile page first.", "blocked")}
    queries = search.expand_queries(state["params"].get("query", ""), profile)
    return {"profile": profile, "trace": _step("Planner", f"Planned searches: {', '.join(queries)}")}


def scout(state: dict) -> dict:
    p = state["params"]
    jobs, report = search.search_jobs(p.get("query", ""), p.get("region", "all"), p.get("location", ""), p.get("scan", 60), profile=state["profile"])
    store.save_results(state["user_id"], jobs, p.get("query", "") or "(my profile)", p.get("region", "all"), p.get("location", ""))
    sources = sum(1 for s in report["sources"].values() if s["count"])
    if not jobs:
        return {"jobs": [], "trace": _step("Job Scout", "No jobs matched. Try a broader search or another region.", "blocked")}
    return {"jobs": jobs, "trace": _step("Job Scout", f"Scanned {len(jobs)} jobs from {sources} sources")}


def matcher(state: dict) -> dict:
    top = sorted(state["jobs"], key=lambda j: j.get("score", 0), reverse=True)[: state["params"].get("prepare", 3)]
    return {"top": top, "trace": _step("Matcher", "Best matches: " + ", ".join(f"{j['title']} ({j['score']}%)" for j in top))}


def write(state: dict) -> dict:
    user_id, profile = state["user_id"], state["profile"]
    for job in state["top"]:
        store.save_draft(user_id, job["id"], "apply", f"{job['title']} @ {job['company']}", f"Apply: {job['title']}", writer.cover_letter(profile, job, user_id=user_id))
    return {"trace": _step("Cover Letter Writer", f"Drafted {len(state['top'])} tailored cover letters")}


def outreach(state: dict) -> dict:
    user_id, profile = state["user_id"], state["profile"]
    for job in state["top"]:
        title = f"{job['title']} @ {job['company']}"
        mail = writer.draft_email(profile, job, user_id)
        store.save_draft(user_id, job["id"], "email", title, mail["subject"], mail["body"])
        store.save_draft(user_id, job["id"], "linkedin", title, "", writer.draft_linkedin(profile, job, user_id))
    return {"trace": _step("Outreach Agent", f"Drafted {len(state['top'])} HR emails and {len(state['top'])} LinkedIn notes")}


def coach(state: dict) -> dict:
    job = state["top"][0]
    prep = generate(state["profile"], job["title"], job["company"], list(job.get("tags") or []) + list(job.get("missing") or []), job.get("description", ""), state["user_id"])
    return {"interview": {"job_id": job["id"], "title": f"{job['title']} @ {job['company']}", **prep}, "trace": _step("Interview Coach", f"Prepared {len(prep['questions'])} practice questions for {job['title']}")}


def gate(state: dict) -> dict:
    waiting = len(store.list_drafts(state["user_id"], status="draft"))
    return {"waiting": waiting, "trace": _step("Approval Gate", f"{waiting} drafts are waiting for your approval. Nothing has been sent.", "waiting")}


NODES = [("planner", planner), ("scout", scout), ("matcher", matcher), ("write", write), ("outreach", outreach), ("coach", coach), ("gate", gate)]


def _merge(state: dict, delta: dict, on_step) -> None:
    for key, value in delta.items():
        if key == "trace":
            state["trace"] += value
            for line in value:
                if on_step:
                    on_step(line)
        else:
            state[key] = value


def _sequential(state: dict, on_step) -> None:
    for key, fn in NODES:
        _merge(state, fn(state), on_step)
        if (key == "planner" and state.get("stop")) or (key == "scout" and not state.get("jobs")):
            break


def _langgraph(state: dict, on_step):
    """Return a callable that runs the LangGraph workflow, or None if LangGraph is unavailable."""
    try:
        from langgraph.graph import END, StateGraph

        class State(TypedDict, total=False):
            user_id: str
            params: dict
            profile: dict
            jobs: list
            top: list
            interview: dict
            waiting: int
            stop: bool
            trace: Annotated[list, operator.add]

        graph = StateGraph(State)
        for key, fn in NODES:
            graph.add_node(key, fn)
        graph.set_entry_point("planner")
        graph.add_conditional_edges("planner", lambda s: "stop" if s.get("stop") else "go", {"stop": END, "go": "scout"})
        graph.add_conditional_edges("scout", lambda s: "go" if s.get("jobs") else "stop", {"stop": END, "go": "matcher"})
        for a, b in [("matcher", "write"), ("write", "outreach"), ("outreach", "coach"), ("coach", "gate"), ("gate", END)]:
            graph.add_edge(a, b)
        app = graph.compile()
    except Exception:  # noqa: BLE001  (not installed or a version difference: use the plain runner)
        return None

    def run() -> None:
        for update in app.stream({"user_id": state["user_id"], "params": state["params"], "trace": []}, stream_mode="updates"):
            for _, delta in update.items():
                _merge(state, delta or {}, on_step)
    return run


def run_agent(user_id: str, params: dict, on_step=None) -> dict:
    state = {"user_id": user_id, "params": params, "trace": []}
    status, engine = "waiting_approval", "sequential"
    try:
        runner = _langgraph(state, on_step)
        if runner:
            engine = "langgraph"
            runner()
        else:
            _sequential(state, on_step)
    except Exception as exc:  # noqa: BLE001
        state["trace"].append({"agent": "Orchestrator", "status": "failed", "message": f"{type(exc).__name__}: {exc}"})
        status = "failed"
    if any(t["status"] == "blocked" for t in state["trace"]):
        status = "blocked"
    summary = {"engine": engine, "top": [{"id": j["id"], "title": j["title"], "company": j["company"], "score": j.get("score", 0)} for j in state.get("top", [])],
               "interview": state.get("interview"), "waiting": state.get("waiting", 0), "scanned": len(state.get("jobs", []))}
    run_id = store.save_run(user_id, params, state["trace"], summary, status)
    return {"id": run_id, "status": status, "trace": state["trace"], "summary": summary}
