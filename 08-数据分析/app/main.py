"""FastAPI 启动入口。

开发：uvicorn app.main:app --reload --port 8000
前端：cd web && npm run dev（Vite 代理 /api → 8000）
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router

app = FastAPI(title="Trader Data", version="0.1.0")

# 开发期允许 Vite (5173) 跨域；生产可收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {"app": "trader-data", "docs": "/docs", "api": "/api/stocks"}
