import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

def carregar_faq_txt(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        linhas = f.read().splitlines()

    perguntas_respostas = []
    pergunta, resposta = None, None

    for linha in linhas:
        if linha.startswith("P:"):
            pergunta = linha[2:].strip().lower()
        elif linha.startswith("R:"):
            resposta = linha[2:].strip()
            if pergunta and resposta:
                perguntas_respostas.append((pergunta, resposta))
                pergunta, resposta = None, None
    return perguntas_respostas

def criar_e_salvar_indice(faq, arquivo_indice, arquivo_perguntas):
    model = SentenceTransformer('all-MiniLM-L6-v2')

    perguntas = [p for p, r in faq]
    embeddings = model.encode(perguntas).astype('float32')

    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)

    faiss.write_index(index, arquivo_indice)

    # Salva perguntas para manter a ordem (para buscar respostas depois)
    with open(arquivo_perguntas, "w", encoding="utf-8") as f:
        for p, r in faq:
            f.write(p + "\t" + r + "\n")

    print(f"Índice criado e salvo em '{arquivo_indice}'.")
    print(f"Perguntas e respostas salvas em '{arquivo_perguntas}'.")

if __name__ == "__main__":
    faq = carregar_faq_txt("faq.txt")
    criar_e_salvar_indice(faq, "faiss.index", "perguntas_respostas.txt")
