"""
src/api/download_api.py
API avec interface utilisateur et orchestration
"""

from flask import Flask, send_file, jsonify, request, render_template_string
import sys
import os
from dotenv import load_dotenv
from datetime import datetime

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
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'annuaire_hydrometrique_{annee}.pdf',
            mimetype='application/pdf'
        )

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/download/<int:annee>', methods=['GET'])
def download_annuaire(annee):
    pdf_path = os.path.join(BASE_DIR, "output", "pdf", f"annuaire_hydrometrique_{annee}.pdf")
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True)
    return jsonify({'status': 'error', 'message': 'PDF non trouvé'}), 404


@app.route('/list', methods=['GET'])
def list_annuaires():
    pdf_dir = os.path.join(BASE_DIR, "output", "pdf")
    files = []
    if os.path.exists(pdf_dir):
        for f in os.listdir(pdf_dir):
            if f.endswith('.pdf'):
                files.append({'fichier': f})
    return jsonify({'status': 'success', 'count': len(files), 'annuaires': files})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    })


# ============================================================
# TEMPLATE HTML
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
                            const annee = f.fichier.match(/\\d+/)?.[0] || '2019';
                            html += `<li style="padding:5px 0; border-bottom:1px solid #eee;">
                                📄 ${f.fichier}
                                <button onclick="downloadPDF(${annee})" class="btn btn-primary" style="padding:2px 10px; font-size:12px; float:right;">
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
    if debug_mode and host == '0.0.0.0':
        print("⚠️  Mode debug actif, accessible depuis tout le réseau local :")
        print("    à réserver à un poste de développement, jamais exposé sur Internet.")
        print("    (réglable via les variables d'environnement FLASK_DEBUG / FLASK_HOST)")
    print("="*60)

    # use_reloader=False : le rechargeur automatique du mode debug
    # redemarrait le serveur en pleine generation de PDF (faux positifs de
    # changement de fichier detectes jusque dans la bibliotheque standard
    # Python - tkinter - sous Windows), interrompant la generation en
    # cours. On garde debug=True pour les pages d'erreur detaillees, sans
    # le rechargement automatique.
    app.run(host=host, port=5000, debug=debug_mode, use_reloader=False)