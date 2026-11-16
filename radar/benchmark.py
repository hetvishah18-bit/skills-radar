"""2026 benchmark: Qarera "Most In-Demand Job Skills of 2026" (360k postings, Dec 2025 - Jun 2026).

Source: https://github.com/dreamjobs-tech/most-in-demand-skills-2026  (CC BY 4.0, attribution: Qarera)
Different extraction method from ours, so compare DIRECTION and RANK, not exact percentages.
"""
from pathlib import Path

import pandas as pd

DIR = Path(__file__).resolve().parent.parent / "benchmarks"

# our role bucket -> Qarera role family
ROLE_MAP = {
    "Data Analyst": "Data Analyst / BI",
    "Business Analyst": "Business Analyst",
    "Data Engineer": "Data Engineer",
    "Software Engineer": "Software Engineer",
    "Project Manager": "Project / Program Mgr",
}

# Qarera label -> our canonical skill (only unambiguous one-to-one matches)
SKILL_MAP = {
    "sql": "SQL", "python": "Python", "power bi": "Power BI", "tableau": "Tableau", "excel": "Excel",
    "aws": "AWS", "azure": "Azure", "gcp": "GCP", "snowflake": "Snowflake", "databricks": "Databricks",
    "statistics": "Statistics", "data modeling": "Data Modeling", "java": "Java",
    "javascript": "JavaScript", "typescript": "TypeScript", "react": "React", "docker": "Docker",
    "kubernetes": "Kubernetes", "git": "Git", "spark": "Spark", "airflow": "Airflow", "dbt": "dbt",
    "kafka": "Kafka", "machine learning": "Machine Learning", "salesforce": "Salesforce",
    "communication": "Communication", "looker": "Looker", "c#": "C#", "go": "Go", "scala": "Scala",
    "etl": "ETL", "jira": "Jira / Agile", "project management": "Project Management",
    "ci/cd": "CI/CD", "microservices": "Microservices", "forecasting": "Forecasting",
}


def available() -> bool:
    return (DIR / "skills-2026-by-role.csv").exists()


def by_role() -> pd.DataFrame:
    df = pd.read_csv(DIR / "skills-2026-by-role.csv")
    df["share"] = df.pct_of_role / 100
    return df


def overall() -> pd.DataFrame:
    df = pd.read_csv(DIR / "skills-2026-overall.csv")
    df["share"] = df.pct_of_all_postings / 100
    return df


def ai_by_seniority() -> pd.DataFrame:
    return pd.read_csv(DIR / "ai-2026-by-seniority.csv")
