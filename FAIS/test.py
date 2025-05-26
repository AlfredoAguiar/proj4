from sentence_transformers import SentenceTransformer, util
import torch

def carregar_faq_txt(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        linhas = f.read().splitlines()

    perguntas_respostas = []
    pergunta, resposta = None, None

    for linha in linhas:
        if linha.startswith("P:"):
            pergunta = linha[2:].strip()
        elif linha.startswith("R:"):
            resposta = linha[2:].strip()
            if pergunta and resposta:
                perguntas_respostas.append((pergunta, resposta))
                pergunta, resposta = None, None
    return perguntas_respostas

model = SentenceTransformer('all-MiniLM-L6-v2')

faq = carregar_faq_txt("faq.txt")
perguntas = [p for p, r in faq]
respostas = [r for p, r in faq]

embeddings_perguntas = model.encode(perguntas, convert_to_tensor=True)

LIMIAR = 0.6

print("Bot iniciado! Pergunte algo (ou digite 'sair' para encerrar):")
while True:
    try:
        entrada = input("Você: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nBot: Até mais!")
        break

    if entrada == "sair":
        print("Bot: Até mais!")
        break

    embedding_usuario = model.encode(entrada, convert_to_tensor=True)
    similaridades = util.cos_sim(embedding_usuario, embeddings_perguntas)

    valor_max = torch.max(similaridades).item()
    indice = torch.argmax(similaridades).item()

    if valor_max >= LIMIAR:
        print(f"Bot (confiança {valor_max:.2f}): {respostas[indice]}")
    else:
        print("Bot: Desculpe, não encontrei uma resposta para sua pergunta.")
