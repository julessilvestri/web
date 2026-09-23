#!/usr/bin/env python3
"""Cerveau Markdown pour llama3.2 (via Ollama) — version 2.

Utilisation :
  python cerveau.py                 chat en terminal
  python cerveau.py --reorganiser   remet en ordre la mémoire existante (à lancer une fois)
"""
import hashlib
import json
import math
import os
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import ollama

# ---------- Réglages ----------
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
CERVEAU = Path(os.environ.get("CERVEAU_DIR", Path(__file__).resolve().parent / "cerveau"))
MODELE = "llama3.2"
MODELE_CONSOLIDATION = "llama3.2"   # un modèle plus gros (ex. qwen2.5:7b) trie mieux, si la RAM suit
MODELE_EMBED = "nomic-embed-text"
TOP_K = 3                 # souvenirs injectés au maximum
SEUIL = 0.5               # similarité minimale pour qu'un souvenir soit injecté
MAX_SOUVENIRS = 1500      # caractères de souvenirs au maximum dans le prompt
HISTORIQUE_MAX = 6        # messages de conversation envoyés au modèle
OPTIONS = {"num_ctx": 4096}
KEEP_ALIVE = "30m"        # garde les modèles chargés en mémoire
CACHE = CERVEAU / ".embeddings.json"
ARCHIVES = CERVEAU / ".archives"
DOSSIERS_RAPPEL = ["01_semantique", "02_episodique", "03_procedurale"]

STRUCTURE = {
    "00_identite/persona.md": "# Persona\n\nTu es un assistant personnel curieux et précis. "
                              "Tu t'appuies sur tes souvenirs quand ils sont pertinents.\n",
    "00_identite/regles.md": "# Règles\n\n- Réponds en français.\n"
                             "- Si tu ne sais pas, dis-le au lieu d'inventer.\n",
    "01_semantique/utilisateur.md": "# Utilisateur\n",
    "03_procedurale/exemple.md": "# Procédure : exemple\n\n1. Étape une\n2. Étape deux\n",
    "04_travail/contexte_actuel.md": "# Contexte actuel\n\nAucune tâche en cours.\n",
}


client = ollama.Client(host=OLLAMA_HOST)


# ---------- Fichiers ----------

def initialiser():
    for dossier in ("02_episodique", ".archives"):
        (CERVEAU / dossier).mkdir(parents=True, exist_ok=True)
    for chemin, contenu in STRUCTURE.items():
        f = CERVEAU / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists():
            f.write_text(contenu, encoding="utf-8")


def lire(f):
    return f.read_text(encoding="utf-8") if f.exists() else ""


def lire_dossier(sous_dossier):
    return "\n\n".join(lire(f) for f in sorted((CERVEAU / sous_dossier).glob("**/*.md")))


def archiver(f):
    """Garde une copie datée avant toute réécriture."""
    if f.exists():
        dest = ARCHIVES / f.relative_to(CERVEAU).parent
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest / f"{f.stem}.{datetime.now():%Y%m%d-%H%M%S}.md")


def sections(texte):
    """Découpe un fichier Markdown en sections '## ' (unités de souvenir)."""
    blocs, courant = [], []
    for ligne in texte.splitlines():
        if ligne.startswith("## ") and courant:
            blocs.append("\n".join(courant))
            courant = []
        courant.append(ligne)
    if courant:
        blocs.append("\n".join(courant))
    return [b.strip()[:1200] for b in blocs if len(b.strip()) > 30]


def morceaux():
    for dossier in DOSSIERS_RAPPEL:
        for f in sorted((CERVEAU / dossier).glob("**/*.md")):
            for bloc in sections(lire(f)):
                yield f"[{f.relative_to(CERVEAU)}]\n{bloc}"


# ---------- Rappel ----------

_cache = None


def cache():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            _cache = {}
    return _cache


def embed(textes):
    return client.embed(model=MODELE_EMBED, input=textes, keep_alive=KEEP_ALIVE)["embeddings"]


def cosinus(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9)


def rappeler(question):
    global _cache
    blocs = list(morceaux())
    if not blocs:
        return ""
    c = cache()
    cles = {b: hashlib.sha1(("doc:" + b).encode()).hexdigest() for b in blocs}
    nouveaux = [b for b in blocs if cles[b] not in c]
    if nouveaux:
        # nomic-embed-text est plus précis avec ces préfixes
        for b, v in zip(nouveaux, embed(["search_document: " + b for b in nouveaux])):
            c[cles[b]] = v
        _cache = {k: c[k] for k in set(cles.values())}      # oublie les blocs disparus
        CACHE.write_text(json.dumps(_cache), encoding="utf-8")
    q = embed(["search_query: " + question])[0]
    classes = sorted(((cosinus(q, _cache[cles[b]]), b) for b in blocs), reverse=True)
    choisis, total = [], 0
    for score, bloc in classes[:TOP_K]:
        if score < SEUIL or total + len(bloc) > MAX_SOUVENIRS:
            continue
        choisis.append(bloc)
        total += len(bloc)
    return "\n\n".join(choisis)


def prompt_systeme(question):
    souvenirs = rappeler(question)
    texte = f"{lire_dossier('00_identite')}\n\n## Mémoire de travail\n{lire_dossier('04_travail')}"
    if souvenirs:
        texte += f"\n\n## Souvenirs pertinents\n{souvenirs}"
    return texte


# ---------- Consolidation ----------

def generer(prompt, json_mode=False):
    r = client.chat(model=MODELE_CONSOLIDATION,
                    messages=[{"role": "user", "content": prompt}],
                    format="json" if json_mode else None,
                    options={**OPTIONS, "temperature": 0.2},
                    keep_alive=KEEP_ALIVE)
    return r["message"]["content"].strip()


def nettoyer_markdown(texte):
    """Retire les ``` que le modèle ajoute parfois autour de sa réponse."""
    texte = re.sub(r"^```[a-z]*\s*\n", "", texte.strip())
    return re.sub(r"\n```\s*$", "", texte).strip() + "\n"


def slug(nom):
    nom = nom.lower().strip().replace(" ", "-").replace("_", "-")
    nom = re.sub(r"[^a-z0-9àâäéèêëîïôöùûüç-]", "", nom).strip("-")
    return nom[:40] or "divers"


def fusionner(fichier, nouveaux_faits):
    """Réécrit une fiche en y intégrant les nouveaux faits (ou la réorganise si aucun)."""
    titre = fichier.stem.replace("-", " ").capitalize()
    ancien = lire(fichier) or f"# {titre}\n"
    infos = "\n".join(f"- {f}" for f in nouveaux_faits) or "(aucune, réorganise seulement la fiche)"
    prompt = (
        "Tu mets à jour une fiche de mémoire en Markdown.\n\n"
        f"Fiche actuelle :\n---\n{ancien}\n---\n\n"
        f"Nouvelles informations :\n{infos}\n\n"
        "Réécris la fiche complète :\n"
        "- garde toutes les informations existantes, sauf si une nouvelle les contredit (remplace-les alors) ;\n"
        "- supprime les doublons et les informations sans intérêt ;\n"
        "- regroupe par thèmes sous des titres « ## » ;\n"
        "- utilise des listes à puces courtes ;\n"
        f"- commence par « # {titre} » ;\n"
        "- réponds uniquement avec le Markdown de la fiche, sans commentaire."
    )
    texte = nettoyer_markdown(generer(prompt))
    # Garde-fou : un petit modèle peut perdre des infos en réécrivant
    trop_court = len(ancien) > 200 and len(texte) < 0.5 * len(ancien)
    if not texte.startswith("#") or trop_court:
        texte = ancien.rstrip() + "\n" + "".join(f"- {f}\n" for f in nouveaux_faits)
    archiver(fichier)
    fichier.write_text(texte, encoding="utf-8")


def consolider(historique):
    if not historique:
        return
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in historique)[-8000:]
    existants = sorted(f.stem for f in (CERVEAU / "01_semantique").glob("*.md"))

    brut = generer(
        "Voici une conversation entre un utilisateur et son assistant.\n"
        f"Fiches de mémoire existantes : {', '.join(existants) or 'aucune'}.\n\n"
        "Réponds uniquement en JSON, au format :\n"
        '{"important": true, "titre": "titre court", "resume": "2 ou 3 phrases", '
        '"faits": [{"fiche": "nom-de-fiche", "fait": "phrase autonome"}]}\n\n'
        "Règles :\n"
        "- important vaut false si rien ne mérite d'être retenu (tests, salutations, bavardage) ;\n"
        "- un fait est durable et compréhensible seul, ex. « L'utilisateur héberge Ollama sur un VPS » ;\n"
        "- réutilise une fiche existante si le sujet correspond, sinon crée un nom court en minuscules avec des tirets ;\n"
        "- 5 faits au maximum.\n\n"
        f"Conversation :\n{transcript}",
        json_mode=True,
    )
    try:
        data = json.loads(brut)
    except json.JSONDecodeError:
        print("Consolidation ignorée : JSON invalide.")
        return
    if not data.get("important"):
        print("Rien d'important à retenir.")
        return

    # Mémoire épisodique : une entrée datée et titrée
    journal = CERVEAU / "02_episodique" / f"{date.today().isoformat()}.md"
    if not journal.exists():
        journal.write_text(f"# Journal du {date.today():%d/%m/%Y}\n", encoding="utf-8")
    with journal.open("a", encoding="utf-8") as f:
        f.write(f"\n## {datetime.now():%H:%M} — {data.get('titre', 'Session')}\n\n"
                f"{str(data.get('resume', '')).strip()}\n")

    # Mémoire sémantique : faits regroupés par fiche puis fusionnés
    par_fiche = {}
    for item in data.get("faits", [])[:5]:
        if isinstance(item, dict) and str(item.get("fait", "")).strip():
            par_fiche.setdefault(slug(str(item.get("fiche", "divers"))), []).append(str(item["fait"]).strip())
    for nom, faits in par_fiche.items():
        fusionner(CERVEAU / "01_semantique" / f"{nom}.md", faits)
    print(f"🧠 Mémorisé : {data.get('titre')} ({sum(map(len, par_fiche.values()))} faits).")


# ---------- Réorganisation de l'existant ----------

def reorganiser():
    print("Réorganisation des fiches…")
    for f in sorted((CERVEAU / "01_semantique").glob("*.md")):
        print(" -", f.name)
        fusionner(f, [])

    print("Compactage des journaux passés…")
    aujourd_hui = date.today().isoformat()
    for j in sorted((CERVEAU / "02_episodique").glob("????-??-??.md")):
        contenu = lire(j)
        if j.stem == aujourd_hui or "<!-- compacté -->" in contenu:
            continue
        print(" -", j.name)
        texte = nettoyer_markdown(generer(
            "Voici le journal d'une journée de conversations.\n"
            "Réécris-le en gardant seulement ce qui est utile à retenir : "
            "une section « ## titre » par sujet, 1 à 3 phrases chacune. "
            "Supprime les tests et le bavardage. Si rien n'est utile, réponds exactement VIDE.\n\n"
            f"{contenu[-8000:]}"
        ))
        archiver(j)
        if texte.strip() == "VIDE":
            j.unlink()
        else:
            j.write_text(f"# Journal du {j.stem}\n<!-- compacté -->\n\n"
                         + re.sub(r"^# .*\n", "", texte), encoding="utf-8")
    print("Terminé. Anciennes versions dans cerveau/.archives/")


# ---------- Chat en terminal ----------

def main():
    historique = []
    print("Cerveau prêt. /sauver pour mémoriser, /quitter pour sortir.")
    while True:
        question = input("\nToi > ").strip()
        if not question:
            continue
        if question in ("/sauver", "/quitter"):
            consolider(historique)
            historique = []
            if question == "/quitter":
                break
            continue
        historique.append({"role": "user", "content": question})
        messages = ([{"role": "system", "content": prompt_systeme(question)}]
                    + historique[-HISTORIQUE_MAX:])
        print("\nIA > ", end="", flush=True)
        reponse = ""
        for part in client.chat(model=MODELE, messages=messages, stream=True,
                                options=OPTIONS, keep_alive=KEEP_ALIVE):
            reponse += part["message"]["content"]
            print(part["message"]["content"], end="", flush=True)
        print()
        historique.append({"role": "assistant", "content": reponse})


if __name__ == "__main__":
    initialiser()
    if "--reorganiser" in sys.argv:
        reorganiser()
    else:
        main()
