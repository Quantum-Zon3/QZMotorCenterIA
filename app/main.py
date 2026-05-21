from contextlib import asynccontextmanager
from time import sleep

from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    last_error = None
    for _ in range(20):
        try:
            with engine.begin() as connection:
                connection.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            sleep(3)

    if last_error is not None:
        raise last_error

    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
