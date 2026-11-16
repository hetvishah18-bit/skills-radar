"""Generate SYNTHETIC demo postings so the dashboard works before you've collected real data.

    python seed_demo.py            # writes data/demo.db
    RADAR_DB=data/demo.db streamlit run app.py

The trends here are made up (e.g. AI-agent skills rising) purely to exercise the charts.
"""
import datetime as dt
import random
from pathlib import Path

from radar import db
from radar.skills import extract_skills

random.seed(42)
DEMO_DB = Path(__file__).resolve().parent / "data" / "demo.db"
WEEKS = 12

COMPANIES = ["Northwind", "Contoso", "Fabrikam", "Globex", "Initech", "Umbrella Analytics",
             "Hooli", "Wayne Data", "Stark Cloud", "Acme Retail"]
CITIES = ["Los Angeles, CA", "Seattle, WA", "Chicago, IL", "Austin, TX", "New York, NY", "Remote"]

# role -> {skill phrase: (start prob, end prob)} -- linear drift over WEEKS
ROLE_PROFILES = {
    "Data Analyst": {
        "SQL": (.85, .85), "Excel": (.70, .62), "Python": (.55, .66), "Tableau": (.45, .34),
        "Power BI": (.40, .48), "statistics": (.40, .42), "dbt": (.08, .16),
        "Snowflake": (.15, .22), "LLMs": (.04, .22), "AI agents": (.01, .12),
        "communication skills": (.50, .50), "A/B testing": (.20, .24), "Looker": (.12, .10),
    },
    "Software Engineer": {
        "Python": (.50, .55), "Java": (.40, .34), "TypeScript": (.30, .40), "React": (.30, .32),
        "AWS": (.45, .48), "Docker": (.35, .38), "Kubernetes": (.25, .28), "REST APIs": (.45, .45),
        "CI/CD": (.30, .33), "LLMs": (.10, .35), "AI agents": (.03, .25), "RAG": (.02, .15),
        "microservices": (.25, .22), "Git": (.40, .40), "Go,": (.10, .13),
    },
    "Business Analyst": {
        "SQL": (.60, .64), "Excel": (.80, .75), "Power BI": (.35, .42), "Tableau": (.30, .25),
        "Jira": (.40, .40), "Agile": (.45, .45), "stakeholder management": (.40, .42),
        "Salesforce": (.15, .15), "Power Automate": (.08, .16), "LLMs": (.03, .14),
    },
    "Data Engineer": {
        "Python": (.85, .85), "SQL": (.85, .85), "Spark": (.55, .52), "Airflow": (.45, .45),
        "dbt": (.25, .38), "Snowflake": (.35, .42), "Databricks": (.30, .40), "AWS": (.50, .50),
        "data modeling": (.40, .42), "Kafka streaming": (.20, .20), "embeddings": (.03, .15),
    },
}
ROLE_WEIGHTS = {"Data Analyst": .35, "Software Engineer": .35, "Business Analyst": .15, "Data Engineer": .15}
TITLES = {
    "Data Analyst": ["Data Analyst", "Data Analyst, New Grad", "Analytics Analyst", "BI Analyst"],
    "Software Engineer": ["Software Engineer", "Software Engineer I", "Full-Stack Software Developer"],
    "Business Analyst": ["Business Analyst", "Business Systems Analyst"],
    "Data Engineer": ["Data Engineer", "Analytics Engineer"],
}


def make_posting(role: str, t: float) -> str:
    phrases = [p for p, (a, b) in ROLE_PROFILES[role].items() if random.random() < a + (b - a) * t]
    return "Requirements: experience with " + ", ".join(phrases) + ". Bachelor's degree preferred."


def main():
    if DEMO_DB.exists():
        DEMO_DB.unlink()
    conn = db.connect(DEMO_DB)
    start = dt.date.today() - dt.timedelta(weeks=WEEKS - 1)
    n = 0
    for w in range(WEEKS):
        t = w / (WEEKS - 1)
        week_start = start + dt.timedelta(weeks=w)
        for _ in range(random.randint(90, 130)):
            role = random.choices(list(ROLE_WEIGHTS), weights=ROLE_WEIGHTS.values())[0]
            desc = make_posting(role, t)
            title = random.choice(TITLES[role])
            n += 1
            job = {
                "job_key": f"demo:{n}", "source": "demo", "company": random.choice(COMPANIES),
                "title": title, "role": role, "location": random.choice(CITIES),
                "url": "", "description": desc,
            }
            seen = (week_start + dt.timedelta(days=random.randint(0, 6))).isoformat()
            db.upsert_job(conn, job, extract_skills(f"{title} {desc}"), seen)
    conn.commit()
    print(f"Wrote {n} synthetic postings over {WEEKS} weeks to {DEMO_DB}")


if __name__ == "__main__":
    main()
