"""
maj_llm_host.py
Met a jour rapidement LLM_HOST (et LLM_MODEL) dans le fichier .env local,
a chaque fois que vous relancez le notebook Colab d'hebergement et que
l'URL du tunnel change.

Usage :
    python maj_llm_host.py https://xxxxx.trycloudflare.com
"""

import sys
import os
import re

def main():
    if len(sys.argv) < 2:
        print("Usage : python maj_llm_host.py <url_du_tunnel>")
        print("Exemple : python maj_llm_host.py https://abc123.trycloudflare.com")
        sys.exit(1)

    nouvelle_url = sys.argv[1].strip().rstrip("/")
    if not nouvelle_url.startswith("http"):
        print("[ERREUR] L'URL doit commencer par http:// ou https://")
        sys.exit(1)

    chemin_env = ".env"
    if not os.path.exists(chemin_env):
        print(f"[ERREUR] {chemin_env} introuvable dans le dossier courant ({os.getcwd()})")
        sys.exit(1)

    with open(chemin_env, "r", encoding="utf-8") as f:
        contenu = f.read()

    if re.search(r"^LLM_HOST=.*$", contenu, re.MULTILINE):
        contenu = re.sub(r"^LLM_HOST=.*$", f"LLM_HOST={nouvelle_url}", contenu, flags=re.MULTILINE)
    else:
        contenu += f"\nLLM_HOST={nouvelle_url}\n"

    if re.search(r"^LLM_MODEL=.*$", contenu, re.MULTILINE):
        contenu = re.sub(r"^LLM_MODEL=.*$", "LLM_MODEL=hydrometrie", contenu, flags=re.MULTILINE)
    else:
        contenu += "LLM_MODEL=hydrometrie\n"

    with open(chemin_env, "w", encoding="utf-8") as f:
        f.write(contenu)

    print(f"[OK] .env mis a jour :")
    print(f"     LLM_HOST={nouvelle_url}")
    print(f"     LLM_MODEL=hydrometrie")
    print("\nRedemarrez votre application Flask/Streamlit pour que le changement soit pris en compte.")


if __name__ == "__main__":
    main()