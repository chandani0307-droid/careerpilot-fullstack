"""Job-specific interview prep: questions, answer tips, topics, STAR stories and questions to ask.

Everything is built from the job (title, company, description, skills) and the candidate's profile,
so two different jobs never get the same sheet.
"""
import re

from services.llm import llm
from services.skills import extract_skills

FRONT = "React,Next.js,Vue,Angular,JavaScript,TypeScript,HTML,CSS,Tailwind CSS,Redux,GraphQL,REST APIs,Testing,Figma,Git"
BACK = "Python,Java,Node.js,FastAPI,Django,Flask,Spring Boot,.NET,C#,Go,REST APIs,Microservices,PostgreSQL,MySQL,MongoDB,Redis,Kafka,Docker,Kubernetes,AWS,SQL,Git,Testing"

# job type -> (words in the job title, skills that make sense for it).
# This list is what stops .NET or Android from showing up for a Data Scientist.
FAMILIES = {
    "analyst": (r"analy|\bbi\b|reporting|insight", "SQL,Excel,Power BI,Tableau,Python,Pandas,NumPy,Statistics,Data Analysis,ETL,PostgreSQL,MySQL,Git"),
    "data": (r"data|machine learning|\bml\b|\bai\b|llm|nlp", "Python,SQL,Pandas,NumPy,Scikit-learn,Machine Learning,Deep Learning,Statistics,TensorFlow,PyTorch,NLP,LLMs,LangChain,RAG,Spark,Airflow,ETL,AWS,GCP,Azure,Docker,Git"),
    "fullstack": (r"full.?stack", FRONT + "," + BACK),
    "frontend": (r"front|\bui\b|react|angular|\bvue", FRONT),
    "backend": (r"back|python|\bjava\b|software|\bapi\b|\.net", BACK),
    "devops": (r"devops|\bsre\b|cloud|platform|infrastructure", "Docker,Kubernetes,Terraform,AWS,Azure,GCP,CI/CD,Linux,Ansible,Bash,Python,Git"),
    "mobile": (r"android|\bios\b|mobile|flutter", "Android,iOS,Flutter,React Native,Kotlin,Swift,Java,REST APIs,Git,Testing"),
    "qa": (r"\bqa\b|quality|test|sdet", "Selenium,Cypress,Testing,Python,Java,JavaScript,SQL,CI/CD,REST APIs,Git"),
}
# one scenario question per job type: (question, answer tip)
SCENARIO = {
    "analyst": ("Two dashboards at {co} show different revenue numbers. What do you do as a {role}?", "Trace the metric definitions, reconcile the rows, agree one definition, and tell the team at {co} what changed."),
    "data": ("Your model scores 0.93 AUC offline but adds no value after launch at {co}. What could be wrong?", "Check target leakage, label definition, data drift and whether the metric matches the business action. Say how you would test it."),
    "fullstack": ("A page at {co} is slow and the API behind it is slow too. How do you find the cause?", "Measure first: browser profile, API traces, slow queries. Fix the biggest cost and show how you would confirm the gain."),
    "frontend": ("A page in {co}'s app feels slow on a mid-range phone. How do you find and fix the cause?", "Profile it, check bundle size and re-renders, then verify the improvement with numbers."),
    "backend": ("An endpoint at {co} became three times slower after a release. How do you debug it?", "Check metrics and traces, the release diff, slow queries and caching. Roll back first if users are hurt."),
    "devops": ("A deploy at {co} causes an error spike. Walk me through your response as a {role}.", "Roll back first, investigate logs and metrics, then add guardrails such as canary releases so it cannot repeat."),
    "mobile": ("A release at {co} crashes for 3% of users. What do you do?", "Halt the rollout, read the crash reports, hotfix or roll back, then find the root cause."),
    "qa": ("The end-to-end tests at {co} are flaky and nobody trusts them. What do you do?", "Quarantine the flaky tests, find the cause (timing, data, environment), fix it and track the flake rate."),
}


def _lines(description: str, required: list[str], ok) -> list[str]:
    """Pick up to two responsibility sentences from the job description."""
    found = []
    for part in re.split(r"\n+|(?<=[.!?])\s+", description or ""):
        part = part.strip(" -*•.;:")
        if 25 <= len(part) <= 160 and re.search(r"\b(build|design|develop|own|lead|analy|create|improve|manage|deploy|work)", part, re.I) \
                and not re.search(r"requirements?:|benefits|apply", part, re.I) and ok(part):
            found.append(re.sub(r"^(you will|you'll)\s+", "", part, flags=re.I))
    found.sort(key=lambda s: -len(set(extract_skills(s)) & set(required)))
    return found[:2]


def generate(profile: dict, role: str, company: str, skills: list[str], description: str = "", user_id: str | None = None) -> dict:
    role = role.strip() or "this role"
    co = company if company and company.lower() not in ("the company", "unknown") else "this company"
    family, allowed = next(((name, set(sk.split(","))) for name, (rx, sk) in FAMILIES.items() if re.search(rx, role.lower())), ("general", None))
    in_title = extract_skills(role)

    def ok(text: str) -> bool:  # True when the text only mentions skills that fit this kind of job
        return allowed is None or all(s in allowed or s in in_title for s in extract_skills(text))

    found = extract_skills(f"{role} {description} {' '.join(skills)}")
    required = [s for s in found if allowed is None or s in allowed or s in in_title][:8]
    mine = set(profile.get("skills") or [])
    matched = [s for s in required if s in mine]
    missing = [s for s in required if s not in mine] if mine else []
    focus = ", ".join(matched[:2] or required[:2]) or role

    qs = [{"question": f"Why {co}, and why this {role} role?", "type": "behavioral",
           "tip": f"Research what {co} builds, then link it to your strongest overlap ({focus}). Keep it under a minute."}]
    for duty in _lines(description, required, ok):
        qs.append({"question": f"The posting says you'll {duty[0].lower() + duty[1:]}. How would you approach that?", "type": "behavioral",
                   "tip": f"Name concrete steps, the tools you would use ({focus}), and how you would measure success at {co}."})
    if family in SCENARIO:
        question, tip = SCENARIO[family]
        qs.append({"question": question.format(co=co, role=role), "type": "technical", "tip": tip.format(co=co, role=role)})
    for s in matched[:3]:
        others = ", ".join([x for x in required if x != s][:2]) or "trade-offs"
        qs.append({"question": f"Tell me about a project where you used {s}. What did you own, and what would you change now?", "type": "technical",
                   "tip": f"Use STAR with one number. Pick the example closest to {role} work at {co}. Expect follow-ups on {others}."})
    for s in missing[:2]:
        qs.append({"question": f"The {role} job at {co} uses {s}, which is not on your resume. How would you become productive with it in a month?", "type": "behavioral",
                   "tip": f"Be honest that it is new. Build on {matched[0] if matched else 'a related skill'} and give a 30-day plan with one small project. Never claim experience you do not have."})
    qs.append({"question": f"Tell me about a project you owned that is closest to what a {role} does at {co}. What would you do differently?", "type": "behavioral",
               "tip": f"Cover the goal, your decisions, one measured result and one lesson. Lean on {focus}."})
    qs.append({"question": f"As {role} at {co}, how would you prioritise your first month when everything feels urgent?", "type": "behavioral",
               "tip": f"Show a simple method (impact versus effort, who is waiting) and say what you would ask your manager at {co} in week one."})

    topics = [f"{s}: core concepts and one real example" + (" (revise first: not on your resume)" if s in missing else "") for s in missing + matched]
    topics += [f"{s}: core concepts and one real example" for s in required if s not in missing + matched]
    prep = {
        "questions": qs[:10],
        "technical_topics": topics[:7] or [f"The core tools listed for the {role} role"],
        "star_stories": [f"A project where you used {focus} to get a measurable result. Pick the one closest to the {role} work at {co}.",
                         "A time something broke or went wrong, how you fixed it and what you changed afterwards.",
                         "A time you worked with other people to land a result, or handled a disagreement."]
                        + ([f"A time you learned something new quickly, ideally to prepare for {missing[0]}, which {co} needs."] if missing else []),
        "questions_to_ask": [f"What does success look like in the first 90 days for this {role} at {co}?",
                             f"How does the team use {(matched or required or [role])[0]} today, and what is hard about it?",
                             "How is work reviewed before it is released?", "What are the biggest challenges for the team right now?"],
        "ai_enhanced": False,
    }

    data = llm.json("You are an interview coach. Be specific to the job. Never invent skills.",
                    "Create interview prep for this job. JSON keys: questions (8 objects with question, type, tip), technical_topics (6 strings), "
                    "star_stories (4 strings), questions_to_ask (4 strings). Every question and tip must be specific to the role, company or listed skills. "
                    f"Only mention technologies from: {', '.join(sorted(allowed)) if allowed else 'the job description'}.\n\n"
                    f"ROLE: {role} at {co}\nREQUIRED SKILLS: {', '.join(required)}\nMISSING SKILLS: {', '.join(missing) or 'none'}\n"
                    f"CANDIDATE SKILLS: {', '.join(sorted(mine))}\nJOB: {description[:1200]}", user_id=user_id) if llm.available else None
    if data:
        good = [q for q in data.get("questions") or [] if isinstance(q, dict) and q.get("question") and q.get("tip") and ok(f"{q['question']} {q['tip']}")]
        if len(good) >= 6:
            prep["questions"] = [{"question": str(q["question"]), "type": str(q.get("type", "technical")), "tip": str(q["tip"])} for q in good][:10]
            prep["ai_enhanced"] = True
        for key in ("technical_topics", "star_stories", "questions_to_ask"):
            items = [str(x) for x in data.get(key) or [] if ok(str(x))]
            if len(items) >= 3:
                prep[key] = items[:7]
    return prep
