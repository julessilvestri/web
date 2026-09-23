# Cerveau Ollama

Chat web (FastAPI + JS) branché sur Ollama, avec une mémoire en Markdown dans `cerveau/`.

## Configuration

```bash
cp .env.example .env   # puis ajuste OLLAMA_HOST, UID, GID
```

Modèles requis côté Ollama : `ollama pull llama3.2 && ollama pull nomic-embed-text`

## Dev (Ollama distant, rechargement auto)

```bash
docker compose up --build
```
→ http://localhost:8000

## Prod (Ollama local au serveur)

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

L'Ollama de l'hôte doit écouter sur l'interface Docker, pas seulement sur 127.0.0.1
(`OLLAMA_HOST=0.0.0.0` dans son service systemd).

## Outils en ligne de commande

```bash
docker compose run --rm app python cerveau.py                  # chat en terminal
docker compose run --rm app python cerveau.py --reorganiser    # réorganise la mémoire
```
