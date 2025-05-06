from flask import Flask, request, render_template, jsonify, send_file, redirect, url_for, flash
import pg8000
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user, login_manager
import os

# Inicializa o Flask e o LoginManager
app_bd = Flask(__name__)
app_bd.secret_key = os.urandom(24)  # Necessário para sessões
login_manager = LoginManager()
login_manager.init_app(app_bd)

# Banco de dados e ambiente
DBNAME = os.getenv('DBNAME')
DBUSERNAME = os.getenv('DBUSERNAME')
DBPASSWORD = os.getenv('DBPASSWORD')
DBHOST = os.getenv('DBHOST')
DBPORT = int(os.getenv('DBPORT', 5432))


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

# Definir rota de login





