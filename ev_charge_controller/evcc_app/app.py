from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import Settings
from .runner import Runner, load_config

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runner = Runner(load_config())
    app.state.runner.start()
    yield
    await app.state.runner.stop()


app = FastAPI(title="EV Charge Controller", lifespan=lifespan)


@app.get("/api/status")
def status():
    return app.state.runner.snapshot()


@app.put("/api/settings")
def put_settings(s: Settings):
    if s.min_amps > s.max_amps:
        s.min_amps = s.max_amps
    app.state.runner.save_settings(s)
    return app.state.runner.snapshot()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
