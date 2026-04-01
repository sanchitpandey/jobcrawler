import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class LlmUsageLog(Base):
    """One row per LLM API call, used for per-user token billing."""

    __tablename__ = "llm_usage_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    # "score" | "cover_letter" | "form_fill" | other
    call_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<LlmUsageLog user={self.user_id} tokens={self.tokens}"
            f" model={self.model} type={self.call_type}>"
        )
