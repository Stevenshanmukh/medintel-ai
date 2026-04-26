from dataclasses import dataclass

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.retrieval import RetrievedChunk


SYSTEM_PROMPT = """You are a clinical analysis assistant reviewing a patient's medical conversation history.

Your job is to answer questions about the patient strictly based on the provided visit excerpts.

Rules you must follow:
1. Use ONLY information from the provided excerpts. Do not invent details, dates, medications, or symptoms.
2. When you cite information, reference the specific visit by date — for example, "(Visit on 2024-09-15)".
3. If the excerpts do not contain enough information to answer, say so plainly. Do not guess.
4. You are not making diagnoses or treatment recommendations. You are summarizing what is in the record.
5. If the user asks for medical advice, redirect them to consult a clinician — but still answer factual questions about the record.
6. Be concise. Clinicians read these. Aim for clarity over comprehensiveness.

When discussing symptom progression, prefer chronological framing ("at the September visit... by January..."). When citing observations, quote them when it adds precision."""


USER_PROMPT_TEMPLATE = """Patient visit excerpts (most relevant first):

{context}

---

Question: {question}

Answer the question using only the excerpts above. Cite visit dates when referencing specific information."""


@dataclass
class ReasoningResult:
    answer: str
    chunks_used: list[RetrievedChunk]
    model: str


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a readable context block for the LLM."""
    if not chunks:
        return "(No relevant excerpts found.)"

    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(
            f"[Excerpt {i}] Visit on {chunk.visit_date}\n"
            f"{chunk.chunk_text}"
        )
    return "\n\n".join(blocks)


def reason(question: str, chunks: list[RetrievedChunk]) -> ReasoningResult:
    """Generate a grounded answer to a question using the retrieved chunks as context."""
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your .env file before querying."
        )

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.1,
        api_key=settings.openai_api_key,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("user", USER_PROMPT_TEMPLATE),
    ])

    context = format_context(chunks)
    messages = prompt.format_messages(context=context, question=question)
    response = llm.invoke(messages)

    return ReasoningResult(
        answer=response.content,
        chunks_used=chunks,
        model="gpt-4o-mini",
    )
