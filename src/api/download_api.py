"""
src/api/download_api.py
API de téléchargement de l'annuaire hydrométrique
"""

from flask import Flask, send_file, jsonify, request
import sys
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_edition import AgentEdition

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    return """
    <html>
        <head>
            <title>Annuaire Hydrométrique DGRE</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; max-width: 800px; margin: auto; }
                h1 { color: #1a5276; }
                .btn { background: #1a5276; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
                .btn:hover { background: #2e86c1; }
                select { padding: 10px; margin: 10px 0; }
                .status { margin: 20px 0; padding: 15px; border-radius: 5px; background: #f0f0f0; }
            </style>
        </head>
        <body>
            <h1>🌊 Annuaire Hydrométrique DGRE</h1>
            <p>Générez et téléchargez l'annuaire hydrométrique pour une année donnée.</p>
            
            <div class="status">
                <strong>📁 Dossier de sortie :</strong> output/pdf/<br>
                <strong>🐳 PostgreSQL :</strong> Docker (localhost:5432)
            </div>
            
            <h2>📥 Télécharger l'annuaire</h2>
            <form action="/generate" method="post">
                <label for="annee">Année :</label>
                <select name="annee" id="annee">
                    <option value="2019">2019</option>
                    <option value="2020">2020</option>
                    <option value="2021">2021</option>
                    <option value="2022">2022</option>
                    <option value="2023">2023</option>
                    <option value="2024">2024</option>
                </select>
                <br><br>
                <button type="submit" class="btn">🚀 Générer et Télécharger</button>
            </form>
            
            <hr>
            
            <h2>📋 Documentation API</h2>
            <ul>
                <li><strong>POST /generate</strong> - Générer l'annuaire</li>
                <li><strong>GET /download/&lt;annee&gt;</strong> - Télécharger l'annuaire</li>
                <li><strong>GET /list</strong> - Lister les années disponibles</li>
            </ul>
        </body>
    </html>
    """

@app.route('/generate', methods=['POST'])
def generate_annuaire():
    """Génère l'annuaire pour une année donnée"""
    
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    
    try:
        annee = int(data.get('annee', 2019))
    except (TypeError, ValueError):
        return jsonify({
            'status': 'error',
            'message': "L'année doit être un nombre entier valide"
        }), 400
    
    try:
        print(f"📄 Génération de l'annuaire {annee}...")
        
        output_dir = os.path.join(BASE_DIR, "output", "pdf")
        
        # Utiliser les variables d'environnement pour la connexion
        agent = AgentEdition(
            annee=annee,
            output_dir=output_dir,
            db_config={
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': os.getenv('DB_PORT', 5432),
                'database': os.getenv('DB_NAME', 'hydrometry'),
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', 'postgres')
            }
        )
        
        try:
            pdf_path = agent.generer_pdf()
            
            if request.is_json:
                return jsonify({
                    'status': 'success',
                    'message': f'Annuaire {annee} généré avec succès',
                    'path': pdf_path,
                    'annee': annee
                })
            else:
                return send_file(
                    pdf_path,
                    as_attachment=True,
                    download_name=f'annuaire_hydrometrique_{annee}.pdf',
                    mimetype='application/pdf'
                )
        finally:
            agent.close()
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        if request.is_json:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
        else:
            return f"""
            <html>
                <body style="font-family: Arial; padding: 20px;">
                    <h1 style="color: red;">❌ Erreur</h1>
                    <p>{str(e)}</p>
                    <pre>{traceback.format_exc()}</pre>
                    <a href="/">Retour à l'accueil</a>
                </body>
            </html>
            """, 500

@app.route('/download/<int:annee>', methods=['GET'])
def download_annuaire(annee):
    """Télécharge l'annuaire pour une année donnée"""
    pdf_path = os.path.join(BASE_DIR, "output", "pdf", f"annuaire_hydrometrique_{annee}.pdf")
    
    if not os.path.exists(pdf_path):
        alt_path = os.path.join(BASE_DIR, "output", "pdf", f"annuaire_{annee}.pdf")
        if os.path.exists(alt_path):
            pdf_path = alt_path
        else:
            return jsonify({
                'status': 'error',
                'message': f'Annuaire {annee} non trouvé. Générez-le d\'abord.'
            }), 404
    
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f'annuaire_hydrometrique_{annee}.pdf',
        mimetype='application/pdf'
    )

@app.route('/list', methods=['GET'])
def list_annuaires():
    """Liste les années disponibles"""
    pdf_dir = os.path.join(BASE_DIR, "output", "pdf")
    files = []
    
    if os.path.exists(pdf_dir):
        for f in os.listdir(pdf_dir):
            if f.endswith('.pdf'):
                files.append({
                    'fichier': f,
                    'path': os.path.join(pdf_dir, f)
                })
    
    return jsonify({
        'status': 'success',
        'count': len(files),
        'annuaires': files
    })

@app.route('/health', methods=['GET'])
def health():
    """Vérification de santé"""
    return jsonify({
        'status': 'ok',
        'base_dir': BASE_DIR,
        'output_dir': os.path.join(BASE_DIR, "output", "pdf"),
        'db_host': os.getenv('DB_HOST', 'localhost'),
        'db_port': os.getenv('DB_PORT', 5432),
        'db_name': os.getenv('DB_NAME', 'hydrometry')
    })

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🌊 API Annuaire Hydrométrique DGRE")
    print("="*60)
    print(f"📁 Base : {BASE_DIR}")
    print(f"📁 Sortie : {os.path.join(BASE_DIR, 'output', 'pdf')}")
    print(f"🐳 PostgreSQL : {os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', 5432)}")
    print("📄 Serveur démarré sur http://localhost:5000")
    print("📥 Téléchargement : http://localhost:5000/download/2019")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)