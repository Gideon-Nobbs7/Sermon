from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request) -> Response:
    messenger = request.app.state.whatsapp_messenger
    form = await request.form()
    payload = {key: value for key, value in form.items()}
    twiml = await messenger.handle_update(payload)
    return Response(content=twiml, media_type="application/xml")