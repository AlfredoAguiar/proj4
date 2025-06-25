from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
import os

app = Flask(__name__)
app.secret_key = 'segredo_super_secreto'
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB = {
    "dbname": "chatbot_db",
    "user": "chatbot_user",
    "password": "chatbot_pass",
    "host": "localhost",
    "port": 5433
}

def connect_db():
    return psycopg2.connect(**DB)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/add_faq', methods=['GET', 'POST'])
def add_faq():
    if request.method == 'POST':
        pergunta = request.form['pergunta']
        resposta = request.form['resposta']
        chatbot_id = request.form['chatbot_id']
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO faq (pergunta, resposta, chatbot_id) VALUES (%s, %s, %s)",
                    (pergunta, resposta, chatbot_id))
        conn.commit()
        conn.close()
        flash("FAQ adicionada com sucesso!")
        return redirect(url_for('dashboard'))
    return render_template('add_faq.html')

@app.route('/add_categoria', methods=['GET', 'POST'])
def add_categoria():
    if request.method == 'POST':
        nome = request.form['nome']
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO categoria (nome) VALUES (%s)", (nome,))
        conn.commit()
        conn.close()
        flash("Categoria adicionada com sucesso!")
        return redirect(url_for('dashboard'))
    return render_template('add_categoria.html')

@app.route('/add_documento', methods=['GET', 'POST'])
def add_documento():
    if request.method == 'POST':
        titulo = request.form['titulo']
        chatbot_id = request.form['chatbot_id']
        file = request.files['ficheiro']
        filename = file.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO documento (titulo, ficheiro_path, chatbot_id) VALUES (%s, %s, %s)",
                    (titulo, filepath, chatbot_id))
        conn.commit()
        conn.close()
        flash("Documento carregado com sucesso!")
        return redirect(url_for('dashboard'))
    return render_template('add_documento.html')

@app.route('/add_chatbot', methods=['GET', 'POST'])
def add_chatbot():
    if request.method == 'POST':
        nome = request.form['nome']
        idioma = request.form['idioma']
        descricao = request.form['descricao']
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO Chatbot (nome, idioma, descricao) VALUES (%s, %s, %s)", (nome, idioma, descricao))
        conn.commit()
        conn.close()
        flash("Chatbot criado com sucesso!")
        return redirect(url_for('dashboard'))
    return render_template('add_chatbot.html')


if __name__ == '__main__':
    app.run(debug=True)
