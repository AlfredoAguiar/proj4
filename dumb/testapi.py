from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class MessageRequest(BaseModel):
    message: str
    session_id: str

@app.post("/chat_dumb")
async def chat(req: MessageRequest):
    print(f"Recebido: {req.message}, Sessão: {req.session_id}")
    return {"response": f"Recebido: {req.message}"}
