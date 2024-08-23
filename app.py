from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import json
import traceback
import torch
import ollama
from werkzeug.utils import secure_filename
from document_agent import DocumentAgent

app = Flask(__name__)

# Configuración
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
MODEL_NAME = "llama2-uncensored"
TOP_K_FRAGMENTS = 30
DOCUMENTS_INFO_FILE = 'documents_info.json'

# Asegúrese de que los directorios necesarios existan
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Diccionario para almacenar los agentes de documentos
document_agents = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_documents_info():
    documents_info = {doc_id: {"file_path": agent.file_path} for doc_id, agent in document_agents.items()}
    with open(DOCUMENTS_INFO_FILE, 'w') as f:
        json.dump(documents_info, f)

def load_documents_info():
    if os.path.exists(DOCUMENTS_INFO_FILE):
        with open(DOCUMENTS_INFO_FILE, 'r') as f:
            documents_info = json.load(f)
        for doc_id, info in documents_info.items():
            document_agents[doc_id] = DocumentAgent(doc_id, info['file_path'], MODEL_NAME)

# Cargar información de documentos al inicio
load_documents_info()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_page')
def upload_page():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        doc_id = f"doc{len(document_agents) + 1}"
        
        try:
            agent = DocumentAgent(doc_id, file_path, MODEL_NAME)
            document_agents[doc_id] = agent
            save_documents_info()  # Guardar la información actualizada
            
            print(f"Documento subido y procesado: {doc_id} - {filename}")
            print(f"Número de embeddings generados: {len(agent.vault_embeddings)}")
            print(f"Primeras 5 oraciones del documento:")
            for i, sentence in enumerate(agent.vault_content[:5]):
                print(f"  {i+1}. {sentence[:50]}...")
            
            return jsonify({
                "message": "File uploaded and processed successfully",
                "filename": filename,
                "doc_id": doc_id,
                "sentences_processed": len(agent.vault_content),
                "embeddings_generated": len(agent.vault_embeddings)
            }), 200
        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"Error completo:\n{error_trace}")
            return jsonify({
                "error": f"Error processing file: {str(e)}",
                "traceback": error_trace
            }), 500
    
    return jsonify({"error": "File type not allowed"}), 400

@app.route('/get_documents', methods=['GET'])
def get_documents():
    documents = [{"id": doc_id, "filename": os.path.basename(agent.file_path)} for doc_id, agent in document_agents.items()]
    return jsonify({"documents": documents})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('input')
    doc_ids = data.get('doc_ids', [])
    
    print(f"Recibida consulta: '{user_input}' para los documentos {doc_ids}")
    
    if not doc_ids:
        return jsonify({"error": "No se seleccionaron documentos"}), 400
    
    all_relevant_context = []
    for doc_id in doc_ids:
        if doc_id not in document_agents:
            print(f"Error: ID de documento inválido {doc_id}")
            return jsonify({"error": f"ID de documento inválido: {doc_id}"}), 400
        
        agent = document_agents[doc_id]
        relevant_context = agent.get_relevant_context(user_input, top_k=TOP_K_FRAGMENTS)
        all_relevant_context.extend(relevant_context)
        print(f"Contexto relevante para {doc_id}: {len(relevant_context)} fragmentos")
    
    print(f"Contexto relevante total encontrado: {len(all_relevant_context)} fragmentos")
    
    if not all_relevant_context:
        print("No se encontró contexto relevante")
        return jsonify({"response": "No se encontró información relevante en los documentos seleccionados. Por favor, verifique que el documento contiene información relacionada con su consulta."}), 200
    
    # Usar el primer agente para generar la respuesta
    context_text = [context for context, _ in all_relevant_context]
    unique_context_text = list(dict.fromkeys(context_text))  # Eliminar duplicados preservando el orden
    response = document_agents[doc_ids[0]].generate_response(user_input, unique_context_text)
    
    print(f"Respuesta generada: {response[:100]}...")  # Primeros 100 caracteres de la respuesta
    return jsonify({"response": response}), 200

@app.errorhandler(Exception)
def handle_exception(e):
    response = {
        "error": str(e),
        "message": "An unexpected error occurred."
    }
    return jsonify(response), 500

if __name__ == '__main__':
    # Usar localhost
    app.run(debug=True, host='127.0.0.1', port=5000)

    # O usar todas las interfaces de red disponibles
    # app.run(debug=True, host='0.0.0.0', port=5000)
