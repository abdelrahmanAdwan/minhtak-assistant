"""One typed error family for the whole assistant.

Every failure the user can cause or the network can inflict gets a class here
with an HTTP status and an Arabic message the UI can show as-is. The rule the
whole app follows: **the user never sees a stack trace, and the server never
turns a real failure into a silently wrong answer.**
"""

from __future__ import annotations


class AssistantError(Exception):
    """Base class. `status` is the HTTP code, `user_message` is Arabic text
    safe to render directly in the chat window."""

    status: int = 500
    user_message: str = "حدث خطأ غير متوقع. حاول مرة أخرى."

    def __init__(self, detail: str = "", user_message: str | None = None):
        super().__init__(detail or self.user_message)
        self.detail = detail
        if user_message:
            self.user_message = user_message


class ConfigurationError(AssistantError):
    """The server is missing a key -- an operator problem, not a user one."""

    status = 503
    user_message = "الخدمة غير مهيأة بالكامل. يرجى المحاولة لاحقًا."


class BadRequest(AssistantError):
    status = 400
    user_message = "الطلب غير صالح."


class SessionExpired(AssistantError):
    """The in-memory session is gone (restart or TTL). The UI starts a fresh
    one and says so, rather than pretending the assistant forgot."""

    status = 404
    user_message = "انتهت صلاحية الجلسة. بدأنا محادثة جديدة — أعد إرسال رسالتك."


class UploadRejected(AssistantError):
    status = 413
    user_message = "الملف كبير جدًا أو غير مقبول."


class DocumentUnreadable(AssistantError):
    status = 422
    user_message = (
        "تعذّرت قراءة الملف. تأكد أنه PDF يحتوي نصًا (الملفات الممسوحة ضوئيًا "
        "كصور لا تحتوي نصًا قابلًا للاستخراج)."
    )


class UpstreamUnavailable(AssistantError):
    """Gemini or a tool's backend is down. Distinct from a wrong answer."""

    status = 502
    user_message = "تعذّر الوصول إلى الخدمة الذكية حاليًا. حاول بعد قليل."


class AgentStalled(AssistantError):
    """The tool loop hit its step ceiling without producing an answer. We fail
    loudly instead of fabricating a reply."""

    status = 504
    user_message = "لم أتمكن من إنهاء الإجابة. حاول تبسيط سؤالك أو تقسيمه."
