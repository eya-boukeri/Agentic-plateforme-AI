"""
src/api/download_api.py
API avec interface utilisateur et orchestration
"""

from flask import Flask, send_file, jsonify, request, render_template_string
import sys
import os
from dotenv import load_dotenv
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_orchestrator import AgentOrchestrator

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_db_config():
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'hydrometry'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres')
    }


# Un seul orchestrateur, partagé entre toutes les requêtes : les agents
# (et donc leurs connexions PostgreSQL) sont créés une fois puis réutilisés,
# au lieu d'ouvrir une nouvelle connexion à chaque appel HTTP.
orchestrator = AgentOrchestrator(get_db_config())

# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/chat', methods=['POST'])
def chat():
    """Endpoint de chat avec l'orchestrateur RAG"""
    try:
        data = request.get_json()
        user_input = data.get('question', '').strip()
        
        if not user_input:
            return jsonify({
                'status': 'error',
                'message': 'Veuillez poser une question.'
            })
        
        # Réutilise l'agent RAG déjà chargé (connexion + éventuel LLM
        # partagés), au lieu d'en recréer un nouveau à chaque question.
        rag = orchestrator.get_agent('rag')
        answer = rag.answer(user_input)
        return jsonify({
            'status': 'success',
            'answer': answer
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/generate', methods=['POST'])
def generate_annuaire():
    """Génère l'annuaire PDF"""
    try:
        annee = int(request.form.get('annee', 2019))
        
        # Réutilise l'agent Édition déjà chargé (même connexion), on
        # ajuste juste l'année ciblée avant de générer.
        agent = orchestrator.get_agent('edition')
        agent.annee = annee

        pdf_path = agent.generer_pdf()
        
        # 🔧 CORRECTION : Vérifier que le chemin est absolu et correct
        if not os.path.isabs(pdf_path):
            pdf_path = os.path.join(BASE_DIR, pdf_path)
        
        # Vérifier que le fichier existe
        if not os.path.exists(pdf_path):
            # Chercher dans le répertoire output/pdf
            alt_path = os.path.join(BASE_DIR, "output", "pdf", f"annuaire_hydrometrique_{annee}.pdf")
            if os.path.exists(alt_path):
                pdf_path = alt_path
            else:
                raise FileNotFoundError(f"PDF non trouvé: {pdf_path}")
        
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'annuaire_hydrometrique_{annee}.pdf',
            mimetype='application/pdf'
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/download/<int:annee>', methods=['GET'])
def download_annuaire(annee):
    """Télécharge un PDF existant"""
    # 🔧 CORRECTION : Utiliser BASE_DIR au lieu de src/api
    pdf_path = os.path.join(BASE_DIR, "output", "pdf", f"annuaire_hydrometrique_{annee}.pdf")
    
    # Vérifier aussi dans le chemin alternatif
    if not os.path.exists(pdf_path):
        alt_path = os.path.join(BASE_DIR, "src", "api", "output", "pdf", f"annuaire_hydrometrique_{annee}.pdf")
        if os.path.exists(alt_path):
            pdf_path = alt_path
        else:
            return jsonify({'status': 'error', 'message': f'PDF {annee} non trouvé'}), 404
    
    return send_file(pdf_path, as_attachment=True, download_name=f'annuaire_hydrometrique_{annee}.pdf')


@app.route('/list', methods=['GET'])
def list_annuaires():
    """Liste tous les PDF disponibles"""
    # 🔧 CORRECTION : Utiliser BASE_DIR
    pdf_dir = os.path.join(BASE_DIR, "output", "pdf")
    files = []
    
    # Vérifier aussi dans le chemin alternatif
    if not os.path.exists(pdf_dir):
        alt_dir = os.path.join(BASE_DIR, "src", "api", "output", "pdf")
        if os.path.exists(alt_dir):
            pdf_dir = alt_dir
    
    if os.path.exists(pdf_dir):
        for f in os.listdir(pdf_dir):
            if f.endswith('.pdf'):
                # Extraire l'année du nom du fichier
                annee = f.replace('annuaire_hydrometrique_', '').replace('.pdf', '')
                files.append({
                    'fichier': f,
                    'annee': annee
                })
        # Trier par année décroissante
        files.sort(key=lambda x: x['annee'], reverse=True)
    
    return jsonify({
        'status': 'success', 
        'count': len(files), 
        'annuaires': files
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    })


# ============================================================
# ROUTES POUR L'ANNUAIRE DES STATIONS PAR GOUVERNORAT
# ============================================================

@app.route('/api/stations', methods=['GET'])
def get_all_stations():
    """Récupère toutes les stations avec leurs métadonnées"""
    try:
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # ✅ CORRECTION : Utiliser "station" au lieu de "stations"
        cur.execute("""
            SELECT 
                DISTINCT s.code_station,
                s.nom_station,
                s.gouvernorat,
                s.code_gouvernorat,
                s.bassin,
                s.code_bassin,
                s.cours_eau,
                s.latitude,
                s.longitude,
                s.municipalite,
                s.etat_station,
                s.date_mise_en_service
            FROM station s
            WHERE s.gouvernorat IS NOT NULL AND s.gouvernorat != ''
            ORDER BY s.gouvernorat, s.nom_station
        """)
        
        stations = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': stations,
            'count': len(stations)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stations/gouvernorat', methods=['GET'])
def get_stations_by_governorat():
    """Retourne les stations groupées par gouvernorat"""
    try:
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # ✅ CORRECTION : Utiliser "station" au lieu de "stations"
        cur.execute("""
            SELECT 
                s.gouvernorat,
                s.code_gouvernorat,
                COUNT(*) as nb_stations,
                json_agg(
                    json_build_object(
                        'code', s.code_station,
                        'nom', s.nom_station,
                        'bassin', s.bassin,
                        'code_bassin', s.code_bassin,
                        'cours_eau', s.cours_eau,
                        'latitude', s.latitude,
                        'longitude', s.longitude,
                        'municipalite', s.municipalite,
                        'etat', s.etat_station,
                        'date_mise_service', s.date_mise_en_service
                    ) ORDER BY s.nom_station
                ) as stations
            FROM station s
            WHERE s.gouvernorat IS NOT NULL AND s.gouvernorat != ''
            GROUP BY s.gouvernorat, s.code_gouvernorat
            ORDER BY s.gouvernorat
        """)
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        # Formater les données
        grouped_data = {}
        total_stations = 0
        
        for row in results:
            governorat = row['gouvernorat']
            grouped_data[governorat] = {
                'code_gouvernorat': row['code_gouvernorat'],
                'nb_stations': row['nb_stations'],
                'stations': row['stations']
            }
            total_stations += row['nb_stations']
        
        return jsonify({
            'success': True,
            'data': grouped_data,
            'total_gouvernorats': len(results),
            'total_stations': total_stations
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/annuaire')
def annuaire_page():
    """Page d'annuaire des stations par gouvernorat"""
    return render_template_string(ANNUAIRE_TEMPLATE)


# ============================================================
# TEMPLATE HTML PRINCIPAL
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🌊 Annuaire Hydrométrique DGRE</title>
    <meta charset="UTF-8">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: #f0f4f8; 
            padding: 20px; 
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: linear-gradient(135deg, #1a5276, #2e86c1);
            color: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 30px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .header p { opacity: 0.9; }
        
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
        .card {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .card h2 { 
            color: #1a5276; 
            margin-bottom: 15px;
            border-bottom: 2px solid #e8ecf1;
            padding-bottom: 10px;
        }
        
        .chat-box {
            height: 400px;
            overflow-y: auto;
            border: 1px solid #e8ecf1;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 15px;
            background: #fafbfc;
        }
        .message {
            margin-bottom: 12px;
            padding: 10px 15px;
            border-radius: 10px;
            max-width: 85%;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .message.user {
            background: #1a5276;
            color: white;
            margin-left: auto;
            text-align: right;
        }
        .message.agent {
            background: #e8ecf1;
            color: #1a1a1a;
            margin-right: auto;
        }
        .message.error {
            background: #fde8e8;
            color: #c0392b;
            border: 1px solid #f5c6c6;
        }
        
        .input-group { display: flex; gap: 10px; }
        .input-group input {
            flex: 1;
            padding: 12px 18px;
            border: 2px solid #e8ecf1;
            border-radius: 10px;
            font-size: 14px;
        }
        .input-group input:focus { outline: none; border-color: #2e86c1; }
        
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        .btn-primary { background: #1a5276; color: white; }
        .btn-primary:hover { background: #2e86c1; }
        .btn-success { background: #27ae60; color: white; }
        .btn-success:hover { background: #2ecc71; }
        .btn-secondary { background: #6c757d; color: white; }
        .btn-secondary:hover { background: #5a6268; }
        
        .quick-questions {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 15px;
        }
        .quick-questions button {
            padding: 6px 14px;
            border: 1px solid #2e86c1;
            border-radius: 20px;
            background: white;
            color: #2e86c1;
            cursor: pointer;
            font-size: 12px;
        }
        .quick-questions button:hover {
            background: #2e86c1;
            color: white;
        }
        
        .status {
            margin: 15px 0;
            padding: 12px;
            border-radius: 8px;
            background: #e8f8f5;
            border-left: 4px solid #27ae60;
        }
        
        .nav-links {
            display: flex;
            gap: 10px;
            margin-top: 15px;
            flex-wrap: wrap;
        }
        .nav-links a {
            color: white;
            text-decoration: none;
            padding: 8px 16px;
            background: rgba(255,255,255,0.2);
            border-radius: 8px;
            transition: background 0.3s;
        }
        .nav-links a:hover {
            background: rgba(255,255,255,0.3);
        }
        
        @media (max-width: 768px) {
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌊 Annuaire Hydrométrique DGRE</h1>
            <p>Plateforme de génération d'annuaire et assistant hydrométrique</p>
            <div class="nav-links">
                <a href="/annuaire">🏛️ Voir l'annuaire des stations</a>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>📄 Génération PDF</h2>
                <form action="/generate" method="post">
                    <div style="margin-bottom: 15px;">
                        <label style="display:block; margin-bottom:5px; font-weight:bold;">Année :</label>
                        <select name="annee" style="width:100%; padding:10px; border-radius:10px; border:2px solid #e8ecf1;">
                            <option value="2019">2019-2020</option>
                            <option value="2020">2020-2021</option>
                            <option value="2021">2021-2022</option>
                            <option value="2022">2022-2023</option>
                            <option value="2023">2023-2024</option>
                            <option value="2024">2024-2025</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-success" style="width:100%;">🚀 Générer PDF</button>
                </form>
                <hr style="margin: 15px 0;">
                <button onclick="listPDFs()" class="btn btn-primary" style="width:100%;">📋 Voir les PDF disponibles</button>
                <div id="pdfList" style="margin-top: 10px;"></div>
            </div>
            
            <div class="card">
                <h2>🤖 Assistant Hydrométrique</h2>
                <div class="chat-box" id="chatBox">
                    <div class="message agent">
                        👋 Bonjour ! Je suis l'assistant hydrométrique de la DGRE.<br>
                        Je peux répondre à vos questions sur :<br>
                        • Les débits (max, min, moyen)<br>
                        • Les crues<br>
                        • Les stations et gouvernorats<br>
                        • Les volumes écoulés<br>
                        • Les anomalies<br>
                        • Et bien plus encore !
                    </div>
                </div>
                <div class="input-group">
                    <input type="text" id="questionInput" placeholder="Posez votre question..." onkeypress="if(event.key==='Enter') sendQuestion()">
                    <button onclick="sendQuestion()" class="btn btn-primary">Envoyer</button>
                </div>
                <div class="quick-questions">
                    <button onclick="askQuestion('Donne-moi les statistiques générales')">📊 Stats</button>
                    <button onclick="askQuestion('Quel est le débit maximum dans le gouvernorat de Jendouba ?')">🏆 Max</button>
                    <button onclick="askQuestion('Quelles sont les plus grandes crues ?')">🌊 Crues</button>
                    <button onclick="askQuestion('Donne-moi la liste des stations')">📍 Stations</button>
                    <button onclick="askQuestion('Station PONT DE BIZERTE')">🔍 Recherche</button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function sendQuestion() {
            const input = document.getElementById('questionInput');
            const question = input.value.trim();
            if (!question) return;
            
            const chatBox = document.getElementById('chatBox');
            
            const userMsg = document.createElement('div');
            userMsg.className = 'message user';
            userMsg.textContent = question;
            chatBox.appendChild(userMsg);
            input.value = '';
            
            const loading = document.createElement('div');
            loading.className = 'message agent';
            loading.textContent = '⏳ Recherche en cours...';
            loading.id = 'loadingMsg';
            chatBox.appendChild(loading);
            chatBox.scrollTop = chatBox.scrollHeight;
            
            fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: question })
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('loadingMsg')?.remove();
                const agentMsg = document.createElement('div');
                agentMsg.className = data.status === 'success' ? 'message agent' : 'message error';
                agentMsg.textContent = data.answer || data.message || 'Erreur';
                chatBox.appendChild(agentMsg);
                chatBox.scrollTop = chatBox.scrollHeight;
            })
            .catch(error => {
                document.getElementById('loadingMsg')?.remove();
                const errorMsg = document.createElement('div');
                errorMsg.className = 'message error';
                errorMsg.textContent = '❌ Erreur: ' + error.message;
                chatBox.appendChild(errorMsg);
                chatBox.scrollTop = chatBox.scrollHeight;
            });
        }
        
        function askQuestion(q) {
            document.getElementById('questionInput').value = q;
            sendQuestion();
        }
        
        function listPDFs() {
            const div = document.getElementById('pdfList');
            div.innerHTML = '⏳ Chargement...';
            fetch('/list')
                .then(response => response.json())
                .then(data => {
                    if (data.annuaires && data.annuaires.length > 0) {
                        let html = '<ul style="list-style:none; padding:0;">';
                        data.annuaires.forEach(f => {
                            html += `<li style="padding:5px 0; border-bottom:1px solid #eee; display:flex; justify-content:space-between; align-items:center;">
                                📄 ${f.fichier}
                                <button onclick="downloadPDF(${f.annee})" class="btn btn-primary" style="padding:2px 10px; font-size:12px;">
                                    Télécharger
                                </button>
                            </li>`;
                        });
                        html += '</ul>';
                        div.innerHTML = html;
                    } else {
                        div.innerHTML = 'Aucun PDF disponible';
                    }
                })
                .catch(() => div.innerHTML = '❌ Erreur');
        }
        
        function downloadPDF(annee) {
            window.location.href = '/download/' + annee;
        }
    </script>
</body>
</html>
"""


# ============================================================
# TEMPLATE ANNUAIRE DES STATIONS PAR GOUVERNORAT
# ============================================================

ANNUAIRE_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏛️ Annuaire des Stations par Gouvernorat</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f0f4f8;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        /* En-tête */
        .header {
            background: linear-gradient(135deg, #1a5276, #2e86c1);
            color: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 30px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }
        .header h1 { font-size: 28px; }
        .header p { opacity: 0.9; margin-top: 5px; }
        .header-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        /* Stats */
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-card .number {
            font-size: 32px;
            font-weight: bold;
            color: #1a5276;
        }
        .stat-card .label {
            color: #666;
            font-size: 14px;
            margin-top: 5px;
        }
        
        /* Filtres */
        .filters {
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 25px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }
        .filters input {
            flex: 1;
            min-width: 200px;
            padding: 12px 18px;
            border: 2px solid #e8ecf1;
            border-radius: 8px;
            font-size: 14px;
        }
        .filters input:focus {
            outline: none;
            border-color: #2e86c1;
        }
        .filters select {
            padding: 12px 18px;
            border: 2px solid #e8ecf1;
            border-radius: 8px;
            font-size: 14px;
            background: white;
            min-width: 150px;
        }
        
        /* Liste des gouvernorats */
        .gouvernorat-block {
            background: white;
            border-radius: 10px;
            margin-bottom: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
            transition: all 0.3s;
        }
        .gouvernorat-header {
            background: #f8f9fa;
            padding: 15px 25px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.3s;
            border-left: 5px solid #2e86c1;
        }
        .gouvernorat-header:hover {
            background: #e8ecf1;
        }
        .gouvernorat-header .gov-name {
            font-size: 18px;
            font-weight: 600;
            color: #1a5276;
        }
        .gouvernorat-header .gov-count {
            background: #2e86c1;
            color: white;
            padding: 4px 14px;
            border-radius: 20px;
            font-size: 14px;
        }
        .gouvernorat-header .gov-code {
            color: #666;
            font-size: 12px;
            margin-left: 10px;
        }
        .gouvernorat-header .toggle-icon {
            font-size: 20px;
            transition: transform 0.3s;
        }
        .gouvernorat-header .toggle-icon.open {
            transform: rotate(180deg);
        }
        
        .station-list {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.4s ease;
        }
        .station-list.open {
            max-height: 5000px;
        }
        
        .station-item {
            padding: 12px 25px;
            border-bottom: 1px solid #f0f0f0;
            display: grid;
            grid-template-columns: 2fr 1fr 1fr 1fr;
            gap: 15px;
            align-items: center;
            transition: background 0.2s;
        }
        .station-item:hover {
            background: #f8f9fa;
        }
        .station-item:last-child {
            border-bottom: none;
        }
        .station-name {
            font-weight: 500;
            color: #333;
        }
        .station-name .code {
            font-weight: normal;
            color: #999;
            font-size: 12px;
            margin-left: 8px;
        }
        .station-info {
            color: #666;
            font-size: 13px;
        }
        .station-info .label {
            color: #999;
            font-size: 11px;
        }
        .station-status {
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
            text-align: center;
        }
        .station-status.active {
            background: #d4edda;
            color: #155724;
        }
        .station-status.inactive {
            background: #f8d7da;
            color: #721c24;
        }
        .station-status.unknown {
            background: #e2e3e5;
            color: #383d41;
        }
        
        /* Boutons */
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        .btn-primary { background: #1a5276; color: white; }
        .btn-primary:hover { background: #2e86c1; }
        .btn-success { background: #27ae60; color: white; }
        .btn-success:hover { background: #2ecc71; }
        .btn-outline { background: white; color: #1a5276; border: 2px solid #1a5276; }
        .btn-outline:hover { background: #1a5276; color: white; }
        
        /* Loading */
        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        .loading .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #2e86c1;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        /* Responsive */
        @media (max-width: 768px) {
            .header { flex-direction: column; text-align: center; }
            .header-actions { margin-top: 15px; }
            .station-item {
                grid-template-columns: 1fr;
                gap: 5px;
                padding: 15px 20px;
            }
            .filters { flex-direction: column; }
            .filters input, .filters select { width: 100%; }
        }
        
        .no-results {
            text-align: center;
            padding: 40px;
            color: #666;
            font-size: 16px;
        }
        
        .back-link {
            display: inline-block;
            margin-bottom: 20px;
            color: #1a5276;
            text-decoration: none;
            font-weight: 500;
        }
        .back-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Retour à l'accueil</a>
        
        <div class="header">
            <div>
                <h1>🏛️ Annuaire des Stations Hydrométriques</h1>
                <p>Liste complète des stations par gouvernorat</p>
            </div>
            <div class="header-actions">
                <button class="btn btn-success" onclick="exportData()">📥 Exporter les données</button>
                <button class="btn btn-outline" onclick="expandAll()">📂 Tout ouvrir</button>
                <button class="btn btn-outline" onclick="collapseAll()">📁 Tout fermer</button>
            </div>
        </div>
        
        <!-- Statistiques -->
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="number" id="totalStations">-</div>
                <div class="label">📊 Total des stations</div>
            </div>
            <div class="stat-card">
                <div class="number" id="totalGovernorats">-</div>
                <div class="label">🏛️ Gouvernorats</div>
            </div>
            <div class="stat-card">
                <div class="number" id="activeStations">-</div>
                <div class="label">✅ Stations actives</div>
            </div>
            <div class="stat-card">
                <div class="number" id="inactiveStations">-</div>
                <div class="label">❌ Stations inactives</div>
            </div>
        </div>
        
        <!-- Filtres -->
        <div class="filters">
            <input type="text" id="searchInput" placeholder="🔍 Rechercher une station ou un gouvernorat...">
            <select id="statusFilter">
                <option value="all">Tous les statuts</option>
                <option value="active">Actives</option>
                <option value="inactive">Inactives</option>
            </select>
            <button class="btn btn-primary" onclick="resetFilters()">🔄 Réinitialiser</button>
        </div>
        
        <!-- Contenu -->
        <div id="annuaireContent">
            <div class="loading">
                <div class="spinner"></div>
                <p>Chargement des stations...</p>
            </div>
        </div>
    </div>
    
    <script>
        let allData = {};
        let filteredData = {};
        
        async function loadStations() {
            try {
                const response = await fetch('/api/stations/gouvernorat');
                const data = await response.json();
                
                if (!data.success) {
                    throw new Error(data.error || 'Erreur de chargement');
                }
                
                allData = data.data;
                filteredData = {...allData};
                updateStats(data);
                displayStations(filteredData);
                
            } catch (error) {
                document.getElementById('annuaireContent').innerHTML = `
                    <div style="text-align:center;padding:40px;color:red;background:#fde8e8;border-radius:10px;">
                        ❌ Erreur: ${error.message}
                    </div>
                `;
            }
        }
        
        function displayStations(groupedData) {
            const container = document.getElementById('annuaireContent');
            
            if (Object.keys(groupedData).length === 0) {
                container.innerHTML = '<div class="no-results">Aucune station trouvée</div>';
                return;
            }
            
            let html = '';
            
            for (const [gouvernorat, info] of Object.entries(groupedData)) {
                const stations = info.stations || [];
                const nbStations = info.nb_stations || stations.length;
                
                html += `
                    <div class="gouvernorat-block" data-gouvernorat="${gouvernorat}">
                        <div class="gouvernorat-header" onclick="toggleStations(this)">
                            <div>
                                <span class="gov-name">${gouvernorat}</span>
                                <span class="gov-code">${info.code_gouvernorat || ''}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:15px;">
                                <span class="gov-count">${nbStations} station${nbStations > 1 ? 's' : ''}</span>
                                <span class="toggle-icon">▼</span>
                            </div>
                        </div>
                        <div class="station-list open">
                            ${stations.map(station => `
                                <div class="station-item" data-name="${station.nom || ''}">
                                    <div class="station-name">
                                        ${station.nom || 'Sans nom'}
                                        <span class="code">${station.code || ''}</span>
                                    </div>
                                    <div class="station-info">
                                        <span class="label">Bassin:</span> ${station.bassin || '-'}<br>
                                        <span class="label">Cours d'eau:</span> ${station.cours_eau || '-'}
                                    </div>
                                    <div class="station-info">
                                        <span class="label">Municipalité:</span> ${station.municipalite || '-'}<br>
                                        <span class="label">Mise en service:</span> ${station.date_mise_service || '-'}
                                    </div>
                                    <div>
                                        <span class="station-status ${station.etat === 'Actif' ? 'active' : station.etat === 'Inactif' ? 'inactive' : 'unknown'}">
                                            ${station.etat || 'Non renseigné'}
                                        </span>
                                        <br>
                                        <span style="font-size:11px;color:#999;">
                                            ${station.latitude ? `${station.latitude}, ${station.longitude}` : ''}
                                        </span>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }
            
            container.innerHTML = html;
            
            // Appliquer les filtres actuels
            applyFilters();
        }
        
        function toggleStations(header) {
            const list = header.nextElementSibling;
            list.classList.toggle('open');
            const icon = header.querySelector('.toggle-icon');
            if (icon) icon.classList.toggle('open');
        }
        
        function expandAll() {
            document.querySelectorAll('.station-list').forEach(el => el.classList.add('open'));
            document.querySelectorAll('.toggle-icon').forEach(el => el.classList.add('open'));
        }
        
        function collapseAll() {
            document.querySelectorAll('.station-list').forEach(el => el.classList.remove('open'));
            document.querySelectorAll('.toggle-icon').forEach(el => el.classList.remove('open'));
        }
        
        function updateStats(data) {
            document.getElementById('totalStations').textContent = data.total_stations || 0;
            document.getElementById('totalGovernorats').textContent = data.total_gouvernorats || 0;
            
            // Calculer les stats des stations actives/inactives
            let active = 0, inactive = 0;
            for (const [gov, info] of Object.entries(data.data)) {
                (info.stations || []).forEach(s => {
                    if (s.etat === 'Actif') active++;
                    else if (s.etat === 'Inactif') inactive++;
                });
            }
            document.getElementById('activeStations').textContent = active;
            document.getElementById('inactiveStations').textContent = inactive;
        }
        
        function applyFilters() {
            const searchTerm = document.getElementById('searchInput').value.toLowerCase().trim();
            const statusFilter = document.getElementById('statusFilter').value;
            
            const blocks = document.querySelectorAll('.gouvernorat-block');
            
            blocks.forEach(block => {
                const gouvernorat = block.dataset.gouvernorat.toLowerCase();
                const items = block.querySelectorAll('.station-item');
                let hasVisible = false;
                
                items.forEach(item => {
                    const name = item.dataset.name.toLowerCase();
                    const status = item.querySelector('.station-status')?.textContent || '';
                    
                    let matches = true;
                    
                    // Filtre texte
                    if (searchTerm) {
                        matches = name.includes(searchTerm) || gouvernorat.includes(searchTerm);
                    }
                    
                    // Filtre statut
                    if (matches && statusFilter !== 'all') {
                        if (statusFilter === 'active') {
                            matches = status === 'Actif';
                        } else if (statusFilter === 'inactive') {
                            matches = status === 'Inactif';
                        }
                    }
                    
                    item.style.display = matches ? '' : 'none';
                    if (matches) hasVisible = true;
                });
                
                block.style.display = hasVisible ? '' : 'none';
            });
        }
        
        function resetFilters() {
            document.getElementById('searchInput').value = '';
            document.getElementById('statusFilter').value = 'all';
            applyFilters();
            expandAll();
        }
        
        function exportData() {
            // Exporter les données en JSON
            const dataStr = JSON.stringify(allData, null, 2);
            const blob = new Blob([dataStr], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `stations_par_gouvernorat_${new Date().toISOString().split('T')[0]}.json`;
            a.click();
            URL.revokeObjectURL(url);
        }
        
        // Événements de filtrage
        document.getElementById('searchInput').addEventListener('input', applyFilters);
        document.getElementById('statusFilter').addEventListener('change', applyFilters);
        
        // Ouvrir tous les gouvernorats par défaut
        window.onload = () => {
            loadStations();
            setTimeout(expandAll, 500);
        };
    </script>
</body>
</html>
"""


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    import atexit
    atexit.register(orchestrator.close)

    debug_mode = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    host = os.getenv('FLASK_HOST', '0.0.0.0')

    print("\n" + "="*60)
    print("🌊 API Annuaire Hydrométrique DGRE")
    print("="*60)
    print(f"📄 Serveur démarré sur http://{host}:5000")
    print("🤖 Assistant RAG intégré")
    print("🏛️ Annuaire des stations: http://127.0.0.1:5000/annuaire")
    if debug_mode and host == '0.0.0.0':
        print("⚠️  Mode debug actif, accessible depuis tout le réseau local :")
        print("    à réserver à un poste de développement, jamais exposé sur Internet.")
        print("    (réglable via les variables d'environnement FLASK_DEBUG / FLASK_HOST)")
    print("="*60)

    app.run(host=host, port=5000, debug=debug_mode)