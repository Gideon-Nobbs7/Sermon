import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..schemas.qa import Answer

router = APIRouter()


class QueryRequest(BaseModel):
    question: str


@router.post("/query")
async def query_endpoint(body: QueryRequest, request: Request) -> Answer:
    qa = request.app.state.qa
    return await qa.answer(uuid.uuid4().hex, body.question)