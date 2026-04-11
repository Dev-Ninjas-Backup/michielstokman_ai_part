from fastapi import FastAPI
from app.api.v1.endpoints import hello
from app.api.v1.endpoints import routes_ai, routes_auth, routes_payment, routes_subscription

app = FastAPI()

app.include_router(hello.router, prefix="/v1")
app.include_router(routes_ai.router, prefix="/v1", tags=["AI"])
app.include_router(routes_auth.router, prefix="/v1",tags=["Auth"])
app.include_router(routes_payment.router, prefix="/v1", tags=["Payment"])
app.include_router(routes_subscription.router, prefix="/v1", tags=["Subscription"])


