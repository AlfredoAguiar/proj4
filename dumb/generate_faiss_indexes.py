import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Diretório onde estão os arquivos
DATA_DIR = "bots/dumb_faq"
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

# Função para carregar perguntas e respostas
def load_qa_pairs(file_path):
    questions, answers = [], []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if "\t" in line:
                q, a = line.strip().split("\t", 1)
                questions.append(q.strip())
                answers.append(a.strip())
    return questions, answers

# Varre todos os arquivos *_qa_pt.txt e *_qa_en.txt
for file_name in os.listdir(DATA_DIR):
    if file_name.endswith("_qa_pt.txt") or file_name.endswith("_qa_en.txt"):
        lang = "pt" if "_pt" in file_name else "en"
        base_name = file_name.replace(".txt", "")
        txt_path = os.path.join(DATA_DIR, file_name)

        # Carrega QA
        questions, answers = load_qa_pairs(txt_path)
        if not questions:
            print(f"⚠️ Arquivo vazio ou inválido: {file_name}")
            continue

        # Embeddings
        embeddings = model.encode(questions, convert_to_numpy=True)

        # Cria o índice FAISS
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(np.array(embeddings))

        # Salva os arquivos
        index_path = os.path.join(DATA_DIR, f"{base_name}.index")
        answers_path = os.path.join(DATA_DIR, f"{base_name}.answers")

        faiss.write_index(index, index_path)
        with open(answers_path, "w", encoding="utf-8") as f:
            for a in answers:
                f.write(a + "\n")

        print(f"✅ Índice gerado: {index_path} (linguagem: {lang})")

print("🎉 Todos os índices foram gerados.")
