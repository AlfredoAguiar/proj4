import pg8000
from werkzeug.security import generate_password_hash
import os

# Configurações de banco de dados
DBNAME = 't_82ql'
DBUSERNAME =  't'
DBPASSWORD =  'LJth9webo4UzXUXN5TX79dS0AULEh7vF'
DBHOST = 'dpg-d0ct2p8dl3ps73ehq910-a.oregon-postgres.render.com'
DBPORT =  '5432'


# Função de conexão com o banco
def get_db_connection():
    return pg8000.connect(
        user=DBUSERNAME,
        password=DBPASSWORD,
        host=DBHOST,
        port=DBPORT,
        database=DBNAME
    )


# Função para criar o usuário admin
def create_admin_user():
    username = 'admin'
    password = 'admin'
    # Gerar o hash da senha
    password_hash = generate_password_hash(password)


    conn = get_db_connection()
    cursor = conn.cursor()


    try:
        cursor.execute("""
            INSERT INTO users (username, password, is_admin)
            VALUES (%s, %s, TRUE)
        """, (username, password_hash))
        conn.commit()
        print(f"Usuário {username} criado com sucesso!")
    except Exception as e:
        print(f"Erro ao criar o usuário admin: {e}")
    finally:
        cursor.close()
        conn.close()


create_admin_user()
