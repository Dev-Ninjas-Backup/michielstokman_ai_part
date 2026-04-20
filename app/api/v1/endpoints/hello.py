from fastapi import APIRouter
from app.schemas.schema_system import HelloResponse

router = APIRouter()

@router.get("/hello", response_model=HelloResponse)
async def say_hello():
    return {"message": "Hello, World!"}