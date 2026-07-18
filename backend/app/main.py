"""FastAPI アプリ生成と /api ルータ登録の骨組み。"""

from fastapi import APIRouter, FastAPI

api_router = APIRouter(prefix="/api")
# 各エンドポイント (scores / blueprints / omr) のルータは後続 issue でここに登録する


def create_app() -> FastAPI:
    app = FastAPI(title="mc-sheetmusic2jukebox")
    app.include_router(api_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
