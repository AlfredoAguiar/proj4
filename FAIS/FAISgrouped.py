import os
import faiss
from sentence_transformers import SentenceTransformer
import unicodedata

def normalize_text(text):
    text = text.lower()
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    return text

def load_qa_from_file(path):
    questions = []
    answers = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 2:
                questions.append(parts[0])
                answers.append(parts[1])
    return questions, answers

def load_indexes_and_qas(index_folder):
    cat_to_index = {}
    cat_to_questions = {}
    cat_to_answers = {}

    for filename in os.listdir(index_folder):
        if filename.endswith(".index"):
            category = filename.replace(".index", "")
            index_path = os.path.join(index_folder, filename)
            qa_path = os.path.join(index_folder, f"{category}_qa.txt")

            index = faiss.read_index(index_path)
            questions, answers = load_qa_from_file(qa_path)

            cat_to_index[category] = index
            cat_to_questions[category] = questions
            cat_to_answers[category] = answers

    return cat_to_index, cat_to_questions, cat_to_answers

def search_answers(index, model, questions, answers, user_question, threshold=1.0, top_k=3):
    user_embedding = model.encode([user_question]).astype('float32')
    distances, indices = index.search(user_embedding, top_k)
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if dist <= threshold and idx < len(answers):
            results.append((dist, answers[idx]))
    return results

def detect_category(user_input, category_keywords):
    normalized_input = normalize_text(user_input)
    for cat, keywords in category_keywords.items():
        for word in keywords:
            normalized_word = normalize_text(word)
            if normalized_word in normalized_input:
                return cat
    return None

if __name__ == "__main__":
    model = SentenceTransformer('all-MiniLM-L6-v2')
    index_folder = "faiss_indexes"

    cat_to_index, cat_to_questions, cat_to_answers = load_indexes_and_qas(index_folder)

    category_keywords = {
        "academico": ["matricula", "disciplina", "curso", "sistema", "transferencia", "calendario", "declaracao", "creditos", "optativa"],
        "financeiro": ["mensalidade", "boleto", "pagamento", "bolsa", "financeiro", "desconto", "parcelar", "comprovante"],
        "servicos": ["secretaria", "documento", "historico", "carteirinha", "atendimento", "agendar", "certidao", "estagio", "perda"]
    }

    print("Chatbot iniciado! Digite 'exit' para sair.")

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() == "exit":
            print("Bot: Até logo!")
            break

        category = detect_category(user_input, category_keywords)
        if not category or category not in cat_to_index:
            print("Bot: Não consegui detectar uma categoria específica. Por favor, use palavras-chave relacionadas ao assunto.")
            continue

        results = search_answers(
            cat_to_index[category],
            model,
            cat_to_questions[category],
            cat_to_answers[category],
            user_input
        )

        if results:
            print(f"Bot (categoria: {category}):")
            for dist, resp in results:
                print(f"  (distância {dist:.4f}) → {resp}")
        else:
            print("Bot: Desculpe, não encontrei uma resposta adequada.")
