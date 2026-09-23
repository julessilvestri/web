# Cerveau Ollama

Chat web (FastAPI + JS) branché sur Ollama, avec une mémoire en Markdown dans `cerveau/`.

## Configuration

```bash
cp .env.example .env   # puis ajuste OLLAMA_HOST, UID, GID
```

Modèles requis côté Ollama : `ollama pull llama3.2 && ollama pull nomic-embed-text`

## Dev (Ollama du serveur via tunnel SSH, rechargement auto)

```bash
ssh -N -L 11434:localhost:11434 jules@srv852907.hstgr.cloud   # terminal à part
docker compose up --build
```
→ http://localhost:8000  (`.env` : `OLLAMA_HOST=http://127.0.0.1:11434`)

## Prod (Caddy HTTPS + mot de passe, Ollama dans la stack)

Dans `.env` sur le serveur : `UID`/`GID` (commande `id`), `DOMAIN`, `AUTH_USER`, `AUTH_HASH` (voir `.env.example`).

```bash
mkdir -p cerveau                                    # sinon Docker le crée en root
docker run --rm -it caddy:2 caddy hash-password     # génère AUTH_HASH
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```
→ https://srv852907.hstgr.cloud

Ollama n'est publié que sur `127.0.0.1:11434` du serveur (pour le tunnel SSH du dev),
jamais sur internet. Ne jamais publier un port en `-p 11434:11434` : Docker contourne ufw.

## Outils en ligne de commande

```bash
docker compose run --rm app python cerveau.py                  # chat en terminal
docker compose run --rm app python cerveau.py --reorganiser    # réorganise la mémoire
```
