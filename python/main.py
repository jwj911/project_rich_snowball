from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from models import init_db
from routers import auth, products, comments, varieties, kline, realtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from data_collector.init_mock_data import init_mock_data
    init_mock_data()
    from data_collector.scheduler import start_scheduler
    start_scheduler()
    yield
    from data_collector.scheduler import shutdown_scheduler
    shutdown_scheduler()


app = FastAPI(title="期货交流社区 API", version="2.0.0", lifespan=lifespan)

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(comments.router)
app.include_router(varieties.router)
app.include_router(kline.router)
app.include_router(realtime.router)


@app.get("/")
def root():
    return {"message": "期货交流社区 API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
