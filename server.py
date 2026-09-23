#!/usr/bin/env python3
"""Serveur qui relie l'interface web au cerveau Markdown et à Ollama.

Arborescence :
  server.py
  cerveau.py
  cerveau/            (créé automatiquement)
  public/index.html
  public/js/main.js

Lancement : voir README.md (Docker Compose).
"""
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

import cerveau

OLLAMA = cerveau.OLLAMA_HOST

app = FastAPI(title="Cerveau Ollama")
cerveau.initialiser()


@app.get("/api/tags")
async def tags():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{OLLAMA}/api/tags")
        return JSONResponse(r.json(), status_code=r.status_code)
    except httpx.HTTPError as e:
        return JSONResponse({"error": f"Ollama injoignable : {e}"}, status_code=502)


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    historique = [m for m in body.get("messages", []) if m.get("role") in ("user", "assistant")]
    question = next((m["content"] for m in reversed(historique) if m["role"] == "user"), "")

    systeme = await run_in_threadpool(cerveau.prompt_systeme, question)

    payload = {
        "model": body.get("model") or cerveau.MODELE,
        "messages": [{"role": "system", "content": systeme}] + historique[-cerveau.HISTORIQUE_MAX:],
        "stream": True,
        "options": cerveau.OPTIONS,
        "keep_alive": cerveau.KEEP_ALIVE,
    }

    async def flux():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{OLLAMA}/api/chat", json=payload) as r:
                    async for morceau in r.aiter_raw():
                        yield morceau
        except httpx.HTTPError as e:
            yield ('{"error": "Ollama injoignable : %s"}\n' % str(e).replace('"', "'")).encode()

    return StreamingResponse(flux(), media_type="application/x-ndjson")


@app.post("/api/memoire/consolider")
def consolider(body: dict):
    messages = [m for m in body.get("messages", []) if m.get("role") in ("user", "assistant")]
    if messages:
        cerveau.consolider(messages)
    return {"ok": True, "messages": len(messages)}


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent / "public", html=True), name="public")
