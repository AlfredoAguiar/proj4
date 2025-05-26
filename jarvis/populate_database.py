import os
import shutil
import pg8000
import fitz  # PyMuPDF
from io import BytesIO
from dotenv import load_dotenv
from embeddings.embeddings import Embeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_chroma import Chroma

load_dotenv()

VECTOR_DB_OLLAMA_PATH = os.getenv('VECTOR_DB_OLLAMA_PATH', 'chroma_ollama_db')



DBNAME = os.getenv('DBNAME')
DBUSERNAME = os.getenv('DBUSERNAME')
DBPASSWORD = os.getenv('DBPASSWORD')
DBHOST = os.getenv('DBHOST')
DBPORT = int(os.getenv('DBPORT', 5432))

def get_db_connection():
    return pg8000.connect(
        user=DBUSERNAME,
        password=DBPASSWORD,
        host=DBHOST,
        port=DBPORT,
        database=DBNAME
    )

from langchain.schema import Document
from io import BytesIO
import fitz  # PyMuPDF

def load_documents_from_database():
    all_documents = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, file_name, file_data FROM txt_files ORDER BY uploaded_at DESC")
        for file_id, file_name, file_data in cursor.fetchall():
            file_extension = file_name.lower().split('.')[-1]

            try:
                if file_extension == 'pdf':
                    # Converte PDF binário para texto usando PyMuPDF
                    pdf_bytes = BytesIO(file_data)
                    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                        text = ""
                        for page in doc:
                            text += page.get_text()
                elif file_extension == 'txt':
                    text = file_data.decode('utf-8')
                else:
                    print(f"⚠️ Tipo de arquivo não suportado: {file_name}")
                    continue  # Ignora arquivos com extensões desconhecidas

                if text.strip():
                    all_documents.append(Document(
                        page_content=text,
                        metadata={"source": f"db_{file_name}"}
                    ))
            except Exception as file_err:
                print(f"❌ Erro ao processar arquivo {file_name}: {file_err}")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Erro ao carregar arquivos do banco de dados: {e}")
    return all_documents

def load_documents(directory):
    all_documents = []

    # Carregar arquivos do banco
    db_docs = load_documents_from_database()
    all_documents.extend(db_docs)

    # Carregar arquivos .txt locais
    try:
        for filename in os.listdir(directory):
            if filename.endswith(".txt"):
                path = os.path.join(directory, filename)
                loader = TextLoader(path, encoding='utf-8')
                docs = loader.load()
                for doc in docs:
                    doc.metadata["source"] = filename
                all_documents.extend(docs)
    except Exception as e:
        print(f"❌ Erro ao carregar documentos locais: {e}")

    return all_documents

def split_documents(documents: list[Document]):
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=80,
            length_function=len,
            is_separator_regex=False,
        )
        return text_splitter.split_documents(documents)
    except Exception as e:
        print(f"❌ Erro ao dividir documentos: {e}")
        return []

def calculate_chunk_ids(chunks):
    last_page_id = None
    current_chunk_index = 0

    for chunk in chunks:
        source = chunk.metadata.get("source", "unknown")
        current_page_id = f"{source}"

        if current_page_id == last_page_id:
            current_chunk_index += 1
        else:
            current_chunk_index = 0

        chunk_id = f"{current_page_id}:{current_chunk_index}"
        last_page_id = current_page_id
        chunk.metadata["id"] = chunk_id

    return chunks

def add_to_chroma(chunks: list[Document], db):
    chunks_with_ids = calculate_chunk_ids(chunks)

    existing_items = db.get(include=[])
    existing_ids = set(existing_items["ids"])
    print(f"📦 Documentos existentes na DB: {len(existing_ids)}")

    new_chunks = []
    for chunk in chunks_with_ids:
        if chunk.metadata["id"] not in existing_ids:
            new_chunks.append(chunk)

    if new_chunks:
        print(f"➕ Adicionando novos documentos: {len(new_chunks)}")
        new_chunk_ids = [chunk.metadata["id"] for chunk in new_chunks]
        db.add_documents(new_chunks, ids=new_chunk_ids)
    else:
        print("✅ Nenhum novo documento para adicionar")

def clear_database():
    db_path = VECTOR_DB_OLLAMA_PATH
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
        print("🧹 Base de dados limpa!")

def main():
    print("🔁 Processando modelo: ollama")

    try:
        embeddings = Embeddings(model_name="ollama")
        embedding_function = embeddings.get_embedding_function()

        db_path = VECTOR_DB_OLLAMA_PATH
        db = Chroma(persist_directory=db_path, embedding_function=embedding_function)

        db_documents = load_documents_from_database()


        chunks = split_documents(db_documents)
        add_to_chroma(chunks, db)

    except Exception as e:
        print(f"❌ Erro ao processar ollama: {e}")


if __name__ == "__main__":
    # clear_database()  # Descomente se quiser forçar limpeza
    main()
