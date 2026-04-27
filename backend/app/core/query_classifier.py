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
    "compare_visits",
    "trend_over_time",
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

- "compare_visits": The user wants to compare two specific visits or two specific time points. Requires explicit two-anchor language ("compare X and Y", "between X and Y", "versus", "vs", "X compared to Y"). If only one anchor is given (e.g. "what's different about her most recent visit"), still use this intent — we will compare to the immediately preceding visit by default.
  Examples: "Compare her first and most recent visit", "How is her June 2025 visit different from April 2025?", "What changed between visit 3 and visit 5?", "What's different about her last visit?"

- "trend_over_time": The user wants to see the progression or trajectory of a single subject across all visits — getting better, getting worse, frequency changes, severity changes. No explicit two-anchor comparison.
  Examples: "How has her chest pain changed?", "Has her shortness of breath gotten worse?", "Show the progression of her fatigue", "Is her chest tightness improving?"

- "narrative_synthesis": The user wants a synthesized story or analysis across visits — summaries, explanations, multi-symptom narratives. Use this for broad analytical questions that aren't a single-subject trend or a two-visit comparison.
  Examples: "Summarize her cardiac workup", "Tell me her clinical story", "What's been going on with her overall?"

- "unanswerable_or_unsafe": The user is asking for medical advice, treatment recommendations, diagnoses, or information not present in a clinical record (e.g. blood type, family member's history when not in record).
  Examples: "Should she stop taking metoprolol?", "What's her blood type?", "Diagnose her condition"

Distinguishing trend_over_time from compare_visits:
- "Has her chest pain gotten worse?" -> trend_over_time (single subject progression, no specific anchors)
- "Compare her chest pain in April vs June" -> compare_visits (two explicit anchors)
- "How has her chest pain changed since April?" -> compare_visits (one explicit anchor; we will use it as anchor_a and compare to most recent)

Output ONLY a single JSON object with this shape:
{{
  "intent": "<one of the values above>",
  "subject": "<the specific symptom/medication/topic, or null>",
  "anchor_a": "<temporal phrase for first anchor when intent is compare_visits, else null>",
  "anchor_b": "<temporal phrase for second anchor when intent is compare_visits, else null>"
}}

Anchor extraction rules (only when intent is "compare_visits"):
- Extract the temporal phrase verbatim from the question (e.g. "first visit", "April 2025", "her last visit", "visit 3").
- If the question has two explicit anchors, fill both anchor_a and anchor_b in the order they appear.
- If the question has only one anchor (e.g. "what's different about her last visit"), put it in anchor_a and leave anchor_b null. The handler will compare to the previous visit.
- If intent is anything other than "compare_visits", set both anchor fields to null.

Examples:
Q: "What medications is Sarah taking?" -> {{"intent": "current_medications", "subject": null, "anchor_a": null, "anchor_b": null}}
Q: "When did chest pain first appear?" -> {{"intent": "first_occurrence", "subject": "chest pain", "anchor_a": null, "anchor_b": null}}
Q: "How have her symptoms changed over time?" -> {{"intent": "narrative_synthesis", "subject": null, "anchor_a": null, "anchor_b": null}}
Q: "Should she increase her statin?" -> {{"intent": "unanswerable_or_unsafe", "subject": null, "anchor_a": null, "anchor_b": null}}
Q: "Compare her first and last visit" -> {{"intent": "compare_visits", "subject": null, "anchor_a": "first visit", "anchor_b": "last visit"}}
Q: "What's different between April 2025 and June 2025?" -> {{"intent": "compare_visits", "subject": null, "anchor_a": "April 2025", "anchor_b": "June 2025"}}
Q: "What's different about her most recent visit?" -> {{"intent": "compare_visits", "subject": null, "anchor_a": "most recent visit", "anchor_b": null}}
Q: "Has her chest pain gotten worse?" -> {{"intent": "trend_over_time", "subject": "chest pain", "anchor_a": null, "anchor_b": null}}
Q: "Show the progression of her fatigue" -> {{"intent": "trend_over_time", "subject": "fatigue", "anchor_a": null, "anchor_b": null}}

Output ONLY the JSON. No prose, no explanation, no markdown fences."""


@dataclass
class ClassifiedQuery:
    intent: QueryIntent
    subject: str | None
    anchor_a: str | None
    anchor_b: str | None
    raw_response: str


def classify_query(question: str) -> ClassifiedQuery:
    """Classify a user question into a query intent. Single LLM call, ~80 tokens out."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0,
        api_key=settings.openai_api_key,
        max_tokens=200,
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

    valid_intents = {
        "current_medications",
        "first_occurrence",
        "all_mentions",
        "narrative_synthesis",
        "compare_visits",
        "trend_over_time",
        "unanswerable_or_unsafe",
    }

    try:
        parsed = json.loads(content)
        intent = parsed.get("intent", "narrative_synthesis")
        subject = parsed.get("subject")
        anchor_a = parsed.get("anchor_a")
        anchor_b = parsed.get("anchor_b")

        if intent not in valid_intents:
            intent = "narrative_synthesis"

        if subject is not None and not isinstance(subject, str):
            subject = None
        if anchor_a is not None and not isinstance(anchor_a, str):
            anchor_a = None
        if anchor_b is not None and not isinstance(anchor_b, str):
            anchor_b = None

        # Anchors only meaningful for compare_visits — null them otherwise
        if intent != "compare_visits":
            anchor_a = None
            anchor_b = None

        return ClassifiedQuery(
            intent=intent,
            subject=subject,
            anchor_a=anchor_a,
            anchor_b=anchor_b,
            raw_response=content,
        )
    except json.JSONDecodeError:
        return ClassifiedQuery(
            intent="narrative_synthesis",
            subject=None,
            anchor_a=None,
            anchor_b=None,
            raw_response=content,
        )
