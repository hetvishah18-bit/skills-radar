"""Skills taxonomy + extractor.

Each canonical skill maps to a list of regex patterns (case-insensitive, word-bounded).
Add skills here as you notice new ones in postings -- this file IS your model in v1.
"""
import re

# category -> {canonical skill: [patterns]}
TAXONOMY = {
    "Languages": {
        "Python": [r"python"],
        "SQL": [r"sql", r"t-sql", r"pl/sql", r"postgres(?:ql)?", r"mysql"],
        "R": [r"\bR\b(?= (?:programming|language|studio|,|/))", r"rstudio"],
        "JavaScript": [r"javascript", r"\bjs\b", r"node\.?js"],
        "TypeScript": [r"typescript"],
        "Java": [r"java(?!script)"],
        "C#": [r"c#", r"\.net"],
        "Go": [r"golang", r"\bgo\b(?= (?:language|programming|,))"],
        "Scala": [r"scala"],
    },
    "Data & BI": {
        "Excel": [r"excel", r"spreadsheets?"],
        "Power BI": [r"power ?bi", r"dax"],
        "Tableau": [r"tableau"],
        "Looker": [r"looker"],
        "dbt": [r"\bdbt\b"],
        "Snowflake": [r"snowflake"],
        "Databricks": [r"databricks"],
        "Spark": [r"spark", r"pyspark"],
        "Airflow": [r"airflow"],
        "Kafka": [r"kafka"],
        "pandas": [r"pandas"],
        "Statistics": [r"statistic(?:s|al)", r"a/b test(?:ing)?", r"hypothesis test(?:ing)?", r"regression (?:analysis|models?|modell?ing)", r"linear regression", r"logistic regression"],
        "Data Modeling": [r"data model(?:ing|ling)", r"dimensional model", r"star schema"],
        "ETL": [r"etl", r"elt", r"data pipelines?"],
    },
    "AI / ML": {
        "Machine Learning": [r"machine learning", r"\bml\b"],
        "LLMs / GenAI": [r"llms?", r"large language models?", r"generative ai", r"gen ?ai", r"chatgpt", r"gpt-?\d\w*", r"gpt models?", r"openai", r"prompt engineering"],
        "AI Agents": [r"ai agents?", r"agentic", r"multi-agent", r"mcp\b", r"model context protocol"],
        "RAG": [r"\brag\b", r"retrieval[- ]augmented", r"vector (?:db|database|search)", r"embeddings?"],
        "Deep Learning": [r"deep learning", r"pytorch", r"tensorflow", r"neural networks?"],
        "MLOps": [r"mlops", r"model deployment", r"mlflow"],
        "NLP": [r"\bnlp\b", r"natural language processing"],
    },
    "Cloud & Eng": {
        "AWS": [r"aws", r"amazon web services", r"\bs3\b", r"lambda", r"redshift"],
        "Azure": [r"azure"],
        "GCP": [r"gcp", r"google cloud", r"bigquery"],
        "Docker": [r"docker", r"containeri[sz]ation", r"container orchestration"],
        "Kubernetes": [r"kubernetes", r"\bk8s\b"],
        "Git": [r"\bgit\b", r"github", r"gitlab", r"version control"],
        "CI/CD": [r"ci/cd", r"continuous integration", r"github actions"],
        "APIs": [r"rest(?:ful)? apis?", r"\bapis?\b", r"graphql"],
        "React": [r"react(?:\.js)?"],
        "Microservices": [r"microservices?", r"distributed systems?"],
    },
    "Business & Automation": {
        "Power Automate": [r"power automate", r"power platform", r"power apps"],
        "ERP / SAP": [r"\bsap\b", r"\berp\b", r"oracle (?:ebs|fusion|netsuite)", r"netsuite"],
        "Salesforce": [r"salesforce"],
        "Jira / Agile": [r"jira", r"agile", r"scrum"],
        "Project Management": [r"project management", r"pmp", r"stakeholder management"],
        "Forecasting": [r"forecast(?:ing|s)?", r"demand planning"],
        "Communication": [r"communication skills", r"present(?:ing)? (?:findings|insights)", r"storytelling"],
    },
}

SKILL_CATEGORY = {s: cat for cat, skills in TAXONOMY.items() for s in skills}

_COMPILED = {
    skill: re.compile(r"(?<![\w])(?:" + "|".join(pats) + r")(?![\w])", re.IGNORECASE)
    for cat in TAXONOMY.values()
    for skill, pats in cat.items()
}
# R and Go patterns rely on exact case
_COMPILED["R"] = re.compile(r"(?<![\w])(?:R(?=,| programming| language|/| and)|RStudio)(?![\w])")
_COMPILED["Go"] = re.compile(r"(?<![\w])(?:Golang|golang|Go(?=,| programming| language|/))(?![\w])")


_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(text: str) -> str:
    """Strip HTML and unescape common entities so regexes see plain text."""
    import html
    text = html.unescape(text or "")
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text)


def extract_skills(text: str) -> set[str]:
    text = clean_text(text)
    return {skill for skill, rx in _COMPILED.items() if rx.search(text)}
