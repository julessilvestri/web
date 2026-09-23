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

## Prod (Caddy HTTPS + mot de passe, Ollama local au serveur)

Dans `.env` sur le serveur : `DOMAIN`, `AUTH_USER`, `AUTH_HASH` (voir `.env.example`).

```bash
docker run --rm -it caddy:2 caddy hash-password     # génère AUTH_HASH
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```
→ https://srv852907.hstgr.cloud

### Pare-feu du serveur

Ollama doit écouter sur `0.0.0.0` (pour être joignable depuis Docker) mais **pas** depuis internet :

```bash
sudo ufw allow OpenSSH                                          # AVANT d'activer ufw
sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp   # conteneurs Docker → Ollama
sudo ufw deny 11434
sudo ufw enable
```
Les ports 80/443 de Caddy sont publiés par Docker (qui contourne ufw) : rien à ouvrir.

## Outils en ligne de commande

```bash
docker compose run --rm app python cerveau.py                  # chat en terminal
docker compose run --rm app python cerveau.py --reorganiser    # réorganise la mémoire
```
