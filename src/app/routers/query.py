import uuid
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..schemas.qa import Answer

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    k: int = Field(default=5, ge=1, le=20)
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


@router.post("/query")
async def query_endpoint(body: QueryRequest, request: Request) -> Answer:
    qa = request.app.state.qa
    return await qa.answer(body.session_id, body.question, k=body.k)