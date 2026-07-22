"""FastAPI アプリ生成と /api ルータ登録の骨組み。"""

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import blueprints, omr, scores
from app.config import FRONTEND_DIR

api_router = APIRouter(prefix="/api")
api_router.include_router(scores.router)
api_router.include_router(blueprints.router)
api_router.include_router(omr.router)


def create_app() -> FastAPI:
    app = FastAPI(title="mc-sheetmusic2noteblock", lifespan=omr.lifespan)
    app.include_router(api_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # /api と /healthz を登録した後に frontend/ を / へマウントする(先勝ちで共存)。
    # テスト実行時など frontend/ が見つからない環境ではマウントしない
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    return app


app = create_app()
