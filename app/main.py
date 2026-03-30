from fastapi import FastAPI
from app.api.v1.endpoints import hello
from app.api.v1.endpoints import routes_ai

app = FastAPI()

app.include_router(hello.router, prefix="/v1")
app.include_router(routes_ai.router, prefix="/v1")
