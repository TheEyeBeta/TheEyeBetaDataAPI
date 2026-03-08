"""Chat routes for internet-exposed AI data access."""

from fastapi import APIRouter, Depends

from app.api.dependencies.services import get_advisor_service
from app.auth.dependencies import require_scopes
from app.auth.scopes import SCOPE_ADVISOR_READ
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.advisor_service import AdvisorService

router = APIRouter(tags=["advisor"])


@router.post("/api/v1/chat", response_model=ChatResponse)
@router.post("/api/v1/advisor/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    _=Depends(require_scopes([SCOPE_ADVISOR_READ])),
    advisor_service: AdvisorService = Depends(get_advisor_service),
) -> ChatResponse:
    """Answer user question with constrained DB context."""
    return advisor_service.chat(question=request.question, ticker=request.ticker)
