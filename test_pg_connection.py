"""
test_pg_connection.py
Script isole pour diagnostiquer la connexion PostgreSQL sans que l'erreur
Windows/psycopg2 soit masquee par un plantage UnicodeDecodeError.

Usage : placez ce fichier a la racine du projet et lancez :
    python test_pg_connection.py
"""

import sys
import os
import socket

# Force une sortie UTF-8 avec remplacement des caracteres non encodables,
# pour eviter tout plantage silencieux lie a la console Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def log(msg):
    print(msg, flush=True)


log("=" * 60)
log("DEMARRAGE DU TEST DE CONNEXION")
log("=" * 60)

try:
    from dotenv import load_dotenv
    load_dotenv()
    log("[OK] python-dotenv charge et .env lu")
except Exception as e:
    log(f"[ERREUR] impossible de charger dotenv : {e!r}")
    raise SystemExit(1)

HOST = os.getenv("DB_HOST", "localhost")
PORT = int(os.getenv("DB_PORT", 5432))
DB = os.getenv("DB_NAME", "hydrometry")
USER = os.getenv("DB_USER", "postgres")
PASSWORD = os.getenv("DB_PASSWORD", "postgres")

log("-" * 60)
log("Parametres lus depuis .env :")
log(f"  HOST={HOST!r}")
log(f"  PORT={PORT!r}")
log(f"  DB={DB!r}")
log(f"  USER={USER!r}")
log(f"  PASSWORD={PASSWORD!r}  (longueur={len(PASSWORD)})")
log("-" * 60)

# --- Etape 1 : le port est-il seulement joignable (avant meme Postgres) ? ---
log(f"[1/2] Test TCP brut vers {HOST}:{PORT} ...")
try:
    with socket.create_connection((HOST, PORT), timeout=5):
        log(f"[OK] Port TCP {HOST}:{PORT} joignable.")
except Exception as e:
    msg = repr(e).encode("utf-8", errors="replace").decode("utf-8")
    log(f"[ECHEC] Impossible de joindre {HOST}:{PORT} : {msg}")
    log("")
    log(">>> C'est tres probablement la cause racine : le nom d'hote ne se")
    log(">>> resout pas ou rien n'ecoute sur ce port depuis Windows.")
    log(">>> Si Postgres tourne dans Docker, essayez DB_HOST=localhost")
    log(">>> (a condition que le port 5432 soit bien publie : -p 5432:5432).")
    raise SystemExit(1)

# --- Etape 2 : connexion Postgres reelle ---
log(f"[2/2] Test de connexion PostgreSQL (utilisateur={USER!r}) ...")
try:
    import psycopg2
    conn = psycopg2.connect(
        host=HOST, port=PORT, dbname=DB, user=USER, password=PASSWORD,
        client_encoding="utf8", connect_timeout=5,
    )
    log("[OK] Connexion PostgreSQL reussie !")
    conn.close()
except UnicodeDecodeError as e:
    log("[ECHEC] Le driver a renvoye un message d'erreur non-UTF8 (bug connu")
    log("        Windows/psycopg2). Detail brut :")
    log(f"        {e}")
    log("")
    log(">>> Cela confirme que PostgreSQL (ou l'OS) a renvoye un message")
    log(">>> d'erreur localise (accents) que psycopg2 n'arrive pas a decoder.")
    log(">>> Verifiez : le service Postgres est-il demarre ? DB_HOST est-il")
    log(">>> correct ? Le mot de passe/utilisateur sont-ils exacts ?")
except Exception as e:
    msg = repr(e).encode("utf-8", errors="replace").decode("utf-8")
    log(f"[ECHEC] Erreur de connexion PostgreSQL : {msg}")

log("=" * 60)
log("FIN DU TEST")
log("=" * 60)