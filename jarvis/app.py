import app
from flask import Flask, request, render_template, jsonify, redirect, url_for
from llm_.llm_factory import LLMFactory
from retrieval.rag_retriever2 import RAGRetriever2
from dotenv import load_dotenv, set_key
import pg8000
import os


load_dotenv()


VECTOR_DB_OLLAMA_PATH = os.getenv('VECTOR_DB_OLLAMA_PATH')
LLM_MODEL_NAME = os.getenv('LLM_MODEL_NAME')
LLM_MODEL_TYPE = os.getenv('LLM_MODEL_TYPE')
EMBEDDING_MODEL_NAME = os.getenv('EMBEDDING_MODEL_NAME')
NUM_RELEVANT_DOCS = int(os.getenv('NUM_RELEVANT_DOCS'))

ENV_PATH = '.env'
DBNAME = os.getenv('DBNAME')
DBUSERNAME = os.getenv('DBUSERNAME')
DBPASSWORD = os.getenv('DBPASSWORD')
DBHOST = os.getenv('DBHOST')
DBPORT = int(os.getenv('DBPORT', 5432))
app = Flask(__name__)

ALLOWED_EXTENSIONS = {'pdf'}


def get_db_connection():
    return pg8000.connect(
        user=DBUSERNAME,
        password=DBPASSWORD,
        host=DBHOST,
        port=DBPORT,
        database=DBNAME
    )



retriever = None
llm_model = None


def get_vector_db_path(embedding_model_name):

    if embedding_model_name == "ollama":
        return VECTOR_DB_OLLAMA_PATH
    else:
        raise ValueError(f"Unsupported embedding model: {embedding_model_name}")


def initialize_components():

    global retriever, llm_model
    vector_db_path = get_vector_db_path(EMBEDDING_MODEL_NAME)


    if EMBEDDING_MODEL_NAME == "ollama":


        retriever = RAGRetriever2(vector_db_path='chroma-ollama', embedding_model_name=EMBEDDING_MODEL_NAME)
        llm_model = LLMFactory.create_llm(model_type=LLM_MODEL_TYPE, model_name=LLM_MODEL_NAME)
        print(
             f"Instantiating model type: {LLM_MODEL_TYPE} | model name: {LLM_MODEL_NAME} | embedding model: {EMBEDDING_MODEL_NAME}")

initialize_components()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/admin')
def admin():
    return render_template('admin.html',
                           llm_model_name=LLM_MODEL_NAME,
                           llm_model_type=LLM_MODEL_TYPE,
                           embedding_model_name=EMBEDDING_MODEL_NAME,
                           num_relevant_docs=NUM_RELEVANT_DOCS)


@app.route('/update_settings', methods=['POST'])
def update_settings():
    global LLM_MODEL_NAME, LLM_MODEL_TYPE, EMBEDDING_MODEL_NAME, NUM_RELEVANT_DOCS
    LLM_MODEL_NAME = request.form['llm_model_name']
    LLM_MODEL_TYPE = request.form['llm_model_type']
    EMBEDDING_MODEL_NAME = request.form['embedding_model_name']
    NUM_RELEVANT_DOCS = int(request.form['num_relevant_docs'])


    # Update the .env file
    set_key(ENV_PATH, 'LLM_MODEL_NAME', LLM_MODEL_NAME)
    set_key(ENV_PATH, 'LLM_MODEL_TYPE', LLM_MODEL_TYPE)
    set_key(ENV_PATH, 'EMBEDDING_MODEL_NAME', EMBEDDING_MODEL_NAME)
    set_key(ENV_PATH, 'NUM_RELEVANT_DOCS', str(NUM_RELEVANT_DOCS))



    initialize_components()
    print(
        f"Updating model type: {LLM_MODEL_TYPE} | model name: {LLM_MODEL_NAME} | embedding model: {EMBEDDING_MODEL_NAME}")
    return redirect(url_for('admin'))

@app.route('/query', methods=['POST'])
def query():
    query_text = request.json['query_text']
    results = retriever.query(query_text, k=NUM_RELEVANT_DOCS)
    enhanced_context_text, sources = retriever.format_results(results)
    llm_response = llm_model.generate_response(context=enhanced_context_text, question=query_text)
    response_text = f"{llm_response}<br>"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (user_message, bot_response) VALUES (%s, %s)",
            (query_text, llm_response)
        )
        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        app.logger.error(f"Error saving chat history: {e}")

    return jsonify(response=response_text)




def allowed_file(filename):

    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


if __name__ == "__main__":
    app.run(debug=True)


