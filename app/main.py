from fastapi import FastAPI
from app.api.v1.endpoints import hello

app = FastAPI()

app.include_router(hello.router, prefix="/v1")
