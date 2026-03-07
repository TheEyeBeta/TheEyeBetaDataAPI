"""Chat routes for internet-exposed AI data access."""

from fastapi import APIRouter, Depends

from app.core.security import AuthContext, require_auth
from app.db.session import get_db_session
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ai_service import answer_question

router = APIRouter()


@router.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest, _: AuthContext = Depends(require_auth)) -> ChatResponse:
    """Answer user question with constrained DB context."""
    session = get_db_session()
    try:
        answer, context_rows = answer_question(
            session=session,
            question=request.question,
            ticker=request.ticker,
        )
        return ChatResponse(answer=answer, used_ticker=request.ticker, context_rows=context_rows)
    finally:
        session.close()
