from flask import Flask, request, render_template, jsonify, send_file, redirect, url_for, flash
import pg8000
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Banco de dados e ambiente
DBNAME = os.getenv('DBNAME')
DBUSERNAME = os.getenv('DBUSERNAME')
DBPASSWORD = os.getenv('DBPASSWORD')
DBHOST = os.getenv('DBHOST')
DBPORT = int(os.getenv('DBPORT', 5432))

# Inicializa o Flask e o LoginManager
app_bd = Flask(__name__)
app_bd.secret_key = os.urandom(24)
login_manager = LoginManager()
login_manager.init_app(app_bd)

# Conexão com o banco
def get_db_connection():
    return pg8000.connect(
        user=DBUSERNAME,
        password=DBPASSWORD,
        host=DBHOST,
        port=DBPORT,
        database=DBNAME
    )

# Classe para o usuário
class User(UserMixin):
    def __init__(self, id, username, is_admin=False):
        self.id = id
        self.username = username
        self.is_admin = is_admin

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

# Carregar usuário para login_manager
@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, is_admin FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return User(id=user[0], username=user[1], is_admin=user[2])
    return None

# Rota de login
@app_bd.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password, is_admin FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):  # Verifica senha
            user_obj = User(id=user[0], username=user[1], is_admin=user[3])
            login_user(user_obj)
            return redirect(url_for('protected_page'))  # Redireciona para a página protegida

        flash('Usuário ou senha inválidos.')
        return redirect(url_for('login'))

    return render_template('login.html')

# Rota de logout
@app_bd.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Página protegida (somente admin)
@app_bd.route('/protected_page')
@login_required
def protected_page():
    if not current_user.is_admin:
        return redirect(url_for('login'))  # Caso o usuário não seja admin, redireciona para o login
    return render_template('bd.html')  # Página protegida para administradores

# Rota de upload de arquivos
ALLOWED_EXTENSIONS = {'pdf', 'txt'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app_bd.route('/upload', methods=['POST'])
@login_required
def upload_pdf():
    if not current_user.is_admin:
        return redirect(url_for('login'))  # Garantir que apenas administradores possam acessar

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_data = file.read()

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO txt_files (file_name, file_data) VALUES (%s, %s) RETURNING id",
            (filename, file_data)
        )
        pdf_id = cursor.fetchone()[0]

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'message': f'File {filename} uploaded successfully.', 'id': pdf_id}), 200

    return jsonify({'error': 'Invalid file type'}), 400

# Rota para listar arquivos PDF
@app_bd.route('/get_pdfs', methods=['GET'])
@login_required
def get_pdfs():
    if not current_user.is_admin:
        return redirect(url_for('login'))  # Garantir que apenas administradores possam acessar

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, file_name FROM txt_files ORDER BY uploaded_at DESC")
    pdf_files = cursor.fetchall()

    cursor.close()
    conn.close()

    pdf_list = [{'id': pdf[0], 'file_name': pdf[1]} for pdf in pdf_files]
    return jsonify(pdf_list)

# Rota de download de arquivos PDF
@app_bd.route('/download_pdf/<int:pdf_id>', methods=['GET'])
@login_required
def download_pdf(pdf_id):
    if not current_user.is_admin:
        return redirect(url_for('login'))  # Garantir que apenas administradores possam acessar

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT file_name, file_data FROM txt_files WHERE id = %s", (pdf_id,))
    pdf_file = cursor.fetchone()

    cursor.close()
    conn.close()

    if pdf_file:
        filename, file_data = pdf_file
        return send_file(BytesIO(file_data), download_name=filename, as_attachment=True)

    return jsonify({'error': 'File not found'}), 404

# Rota para deletar arquivos
@app_bd.route('/delete', methods=['POST'])
@login_required
def delete_pdf():
    if not current_user.is_admin:
        return redirect(url_for('login'))  # Garantir que apenas administradores possam acessar

    pdf_id = request.json.get('id')

    if not pdf_id:
        return jsonify({'error': 'Invalid PDF ID'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT file_name FROM txt_files WHERE id = %s", (pdf_id,))
    file_entry = cursor.fetchone()

    if file_entry:
        cursor.execute("DELETE FROM txt_files WHERE id = %s", (pdf_id,))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'message': f'File {file_entry[0]} deleted successfully.'}), 200
    else:
        cursor.close()
        conn.close()
        return jsonify({'error': 'File not found'}), 404

# Iniciar o servidor
if __name__ == "__main__":
    app_bd.run(debug=True, host='127.0.0.1', port=5001)
