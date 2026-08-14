"""The only module that talks to Gemini.

Two capabilities, one HTTP shell:

    chat_step()   one generateContent call WITH the tool declarations attached
                  -- the model either answers or asks for a tool
    embed_texts() the embedding call behind the RAG index

Transport failures become `UpstreamUnavailable`, never a fabricated answer.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

import httpx

from . import config
from .errors import ConfigurationError, UpstreamUnavailable

SYSTEM_INSTRUCTION = (
    "أنت مساعد «منحتك» — مرشد للطلاب العرب الباحثين عن منح ماجستير ممولة "
    "بالكامل. لديك أدوات، استخدمها وقرر بنفسك أيها يناسب كل سؤال.\n\n"
    "قواعد صارمة:\n"
    "1. لا تخترع أي معلومة عن منحة. كل اسم منحة أو مبلغ أو موعد نهائي أو رابط "
    "يجب أن يأتي من أدوات منحتك (search_scholarships / browse_catalogue / "
    "get_scholarship_details). إذا لم ترجعه الأداة، قل إنك لا تملكه — ولا تخمّن.\n"
    "2. إذا سأل المستخدم عن منحة باسمها (مثل «تشيفينينغ» أو «إيراسموس» أو «داد») "
    "أو «هل عندكم منحة كذا؟» أو «ما المنح المتوفرة في بريطانيا؟» — استدعِ "
    "browse_catalogue أولًا دائمًا، ولا تنفِ وجود أي منحة اعتمادًا على معرفتك؛ "
    "الكتالوج وحده هو الحكم. لاحظ أن الكتالوج يشمل منحًا «تنافسية» "
    "(غير مضمونة التمويل) لا يظهرها البحث المرتّب افتراضيًا.\n"
    "3. إذا رفع المستخدم ملفًا، فأي سؤال عن محتواه يُجاب عبر "
    "search_uploaded_documents فقط، واذكر أنك استندت إلى الملف. إن لم تجد "
    "الإجابة في المقاطع المسترجعة، قل ذلك صراحةً.\n"
    "4. يمكنك تسلسل الأدوات: تصفّح الكتالوج، ثم اطلب التفاصيل، ثم احسب الميزانية.\n"
    "5. أجب بلغة المستخدم (بالعربية إن كتب بالعربية)، باختصار وبأرقام محددة "
    "مما أرجعته الأدوات.\n"
    "6. منحتك تغطي منح الماجستير لطلاب المنطقة العربية؛ ما عدا ذلك قله بصراحة."
)


def _headers() -> dict[str, str]:
    if not config.GEMINI_API_KEY:
        raise ConfigurationError("GEMINI_API_KEY is not set")
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": config.GEMINI_API_KEY,
    }


def _post(model: str, action: str, body: dict[str, Any]) -> dict[str, Any]:
    url = f"{config.GEMINI_BASE}/{model}:{action}"
    try:
        response = httpx.post(url, headers=_headers(), json=body,
                              timeout=config.REQUEST_TIMEOUT)
    except httpx.HTTPError as exc:
        raise UpstreamUnavailable(f"could not reach Gemini: {exc}") from exc
    if response.status_code >= 400:
        raise UpstreamUnavailable(
            f"Gemini {action} returned {response.status_code}: {response.text[:300]}")
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamUnavailable("Gemini returned a non-JSON response") from exc


def chat_step(contents: list[dict[str, Any]],
              declarations: list[dict[str, Any]]) -> dict[str, Any]:
    """One turn of the tool-calling loop.

    `tool_config.mode = AUTO` leaves tool SELECTION to the model -- that is the
    point of an agent. `thinkingBudget = 0` keeps latency low; the visible tool
    trace is the reasoning users actually need to audit.
    """
    body: dict[str, Any] = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if declarations:
        body["tools"] = [{"function_declarations": declarations}]
        body["tool_config"] = {"function_calling_config": {"mode": "AUTO"}}

    payload = _post(config.GEMINI_MODEL, "generateContent", body)
    candidates = payload.get("candidates")
    if not candidates:
        feedback = json.dumps(payload.get("promptFeedback", {}))[:200]
        raise UpstreamUnavailable(f"Gemini returned no candidates ({feedback})")
    return candidates[0]


def embed_texts(texts: Sequence[str], *,
                task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed a batch of texts for the RAG index.

    `task_type` is RETRIEVAL_DOCUMENT for stored chunks and RETRIEVAL_QUERY for
    the question -- Gemini tunes the vector to the role, which measurably
    improves retrieval over using one generic embedding for both.
    """
    vectors: list[list[float]] = []
    for text in texts:
        payload = _post(
            config.EMBEDDING_MODEL, "embedContent",
            {
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
                "outputDimensionality": config.EMBEDDING_DIM,
            },
        )
        values = (payload.get("embedding") or {}).get("values")
        if not isinstance(values, list) or len(values) != config.EMBEDDING_DIM:
            raise UpstreamUnavailable(
                f"malformed embedding payload: {str(payload)[:120]}")
        vectors.append([float(value) for value in values])
    return vectors
