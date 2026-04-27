import json
from dataclasses import dataclass
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings


QueryIntent = Literal[
    "current_medications",
    "first_occurrence",
    "all_mentions",
    "narrative_synthesis",
    "unanswerable_or_unsafe",
]


CLASSIFIER_SYSTEM_PROMPT = """You are a query intent classifier for a clinical assistant.

Given a question about a patient's medical record, classify it into ONE of these intents:

- "current_medications": The user wants the patient's current medication list.
  Examples: "What is she taking?", "List her current medications", "What drugs is she on?"

- "first_occurrence": The user wants to know when a specific symptom or condition was first mentioned.
  Examples: "When did chest pain start?", "When was X first reported?", "When did her symptoms begin?"

- "all_mentions": The user wants every visit where a specific symptom, medication, or condition was mentioned.
  Examples: "List every visit that mentioned palpitations", "Show all the times she had heartburn"

- "narrative_synthesis": The user wants a synthesized story or analysis across visits — progression, trends, comparisons, summaries, explanations.
  Examples: "How have her symptoms progressed?", "Summarize her cardiac workup", "Has anything improved?"

- "unanswerable_or_unsafe": The user is asking for medical advice, treatment recommendations, diagnoses, or information not present in a clinical record (e.g. blood type, family member's history when not in record).
  Examples: "Should she stop taking metoprolol?", "What's her blood type?", "Diagnose her condition"

Output ONLY a single JSON object with this shape:
{{"intent": "<one of the values above>", "subject": "<the specific symptom/medication/topic, or null>"}}

Examples:
Q: "What medications is Sarah taking?" -> {{"intent": "current_medications", "subject": null}}
Q: "When did chest pain first appear?" -> {{"intent": "first_occurrence", "subject": "chest pain"}}
Q: "How have her symptoms changed over time?" -> {{"intent": "narrative_synthesis", "subject": null}}
Q: "Should she increase her statin?" -> {{"intent": "unanswerable_or_unsafe", "subject": null}}

Output ONLY the JSON. No prose, no explanation, no markdown fences."""


@dataclass
class ClassifiedQuery:
    intent: QueryIntent
    subject: str | None
    raw_response: str


def classify_query(question: str) -> ClassifiedQuery:
    """Classify a user question into a query intent. Single LLM call, ~50 tokens out."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0,
        api_key=settings.openai_api_key,
        max_tokens=120,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", CLASSIFIER_SYSTEM_PROMPT),
        ("user", "{question}"),
    ])

    messages = prompt.format_messages(question=question)
    response = llm.invoke(messages)
    content = response.content.strip()

    if content.startswith("```"):
        content = content.strip("`").lstrip("json").strip()

    try:
        parsed = json.loads(content)
        intent = parsed.get("intent", "narrative_synthesis")
        subject = parsed.get("subject")

        valid_intents = {
            "current_medications", "first_occurrence", "all_mentions",
            "narrative_synthesis", "unanswerable_or_unsafe",
        }
        if intent not in valid_intents:
            intent = "narrative_synthesis"

        if subject is not None and not isinstance(subject, str):
            subject = None

        return ClassifiedQuery(intent=intent, subject=subject, raw_response=content)
    except json.JSONDecodeError:
        return ClassifiedQuery(intent="narrative_synthesis", subject=None, raw_response=content)
