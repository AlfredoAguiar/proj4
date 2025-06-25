import os
import unicodedata
import faiss
import random
from sentence_transformers import SentenceTransformer

# Normaliza texto
def normalize_text(text):
    text = text.lower()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

# Carrega perguntas e respostas
def load_qa_from_file(path):
    questions, answers = [], []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 2:
                questions.append(parts[0])
                answers.append(parts[1])
    return questions, answers

# Carrega categorias e palavras-chave de ficheiro
def load_category_keywords(path):
    category_keywords = {}
    if not os.path.exists(path):
        return category_keywords
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if ":" in line:
                cat, keys = line.strip().split(":", 1)
                keywords = [normalize_text(k.strip()) for k in keys.split(",")]
                category_keywords[cat.strip()] = keywords
    return category_keywords

# Detecta múltiplas categorias
def detect_categories(user_input, category_keywords):
    normalized_input = normalize_text(user_input)
    detected = []
    for cat, keywords in category_keywords.items():
        for word in keywords:
            if word in normalized_input:
                detected.append(cat)
                break
    return detected

# Carrega índices FAISS, QAs e keywords
def load_data(index_folder, lang_suffix):
    cat_to_index = {}
    cat_to_questions = {}
    cat_to_answers = {}

    for filename in os.listdir(index_folder):
        if filename.endswith(f"_qa_{lang_suffix}.txt"):
            category = filename.replace(f"_qa_{lang_suffix}.txt", "")
            qa_path = os.path.join(index_folder, filename)
            index_path = os.path.join(index_folder, f"{category}.index")

            if not os.path.exists(index_path):
                continue

            index = faiss.read_index(index_path)
            questions, answers = load_qa_from_file(qa_path)

            cat_to_index[category] = index
            cat_to_questions[category] = questions
            cat_to_answers[category] = answers

    keywords_path = os.path.join(index_folder, f"categories_{lang_suffix}.txt")
    category_keywords = load_category_keywords(keywords_path)

    return cat_to_index, cat_to_questions, cat_to_answers, category_keywords

# Busca respostas com FAISS
def search_answers(index, model, answers, user_question, top_k=3):
    user_embedding = model.encode([user_question]).astype('float32')
    distances, indices = index.search(user_embedding, top_k)
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < len(answers):
            results.append((dist, answers[idx]))
    return results

# Busca respostas por palavras em comum
def find_answers_ranked(user_input, questions, answers):
    user_norm = normalize_text(user_input)
    scored = []
    for q, a in zip(questions, answers):
        q_norm = normalize_text(q)
        score = sum(1 for word in q_norm.split() if word in user_norm)
        if score > 0:
            scored.append((score, a))
    scored.sort(reverse=True)
    return [a for _, a in scored]

# Feedback negativo
def load_negative_feedback(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return set(normalize_text(line.strip()) for line in f if line.strip())

def is_negative_feedback(user_input, neg_phrases):
    user_norm = normalize_text(user_input)
    return any(phrase in user_norm for phrase in neg_phrases)

# -------------------- Principal --------------------

if __name__ == "__main__":
    model = SentenceTransformer('all-MiniLM-L6-v2')
    index_folder = "faiss_indexes"
    lang_suffix = "pt"  # podes adaptar conforme idioma
    neg_feedback_path = os.path.join(index_folder, f"negative_feedback_{lang_suffix}.txt")

    cat_to_index, cat_to_questions, cat_to_answers, category_keywords = load_data(index_folder, lang_suffix)
    neg_feedback = load_negative_feedback(neg_feedback_path)

    print("Chatbot iniciado! Escreva 'exit' para sair.")

    last_question = ""
    last_possible_answers = []
    last_answer_index = 0
    negative_count = 0

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() == "exit":
            print("Bot: Até logo!")
            break

        if is_negative_feedback(user_input, neg_feedback):
            if last_question:
                negative_count += 1
                if negative_count >= 2:
                    print("Bot: A procurar uma resposta melhor com IA...")
                    detected_cats = detect_categories(last_question, category_keywords)
                    for cat in detected_cats:
                        if cat in cat_to_index:
                            faiss_results = search_answers(cat_to_index[cat], model, cat_to_answers[cat], last_question)
                            if faiss_results:
                                print(f"Bot (IA - {cat}): {faiss_results[0][1]}")
                                break
                    else:
                        print("Bot: Nenhuma resposta alternativa encontrada.")
                    continue
            if last_possible_answers and last_answer_index + 1 < len(last_possible_answers):
                last_answer_index += 1
                print(f"Bot: {last_possible_answers[last_answer_index]}")
            else:
                print("Bot: Não tenho mais respostas disponíveis para essa questão.")
            continue

        # Nova questão
        detected_cats = detect_categories(user_input, category_keywords)
        if not detected_cats:
            print("Bot: Não consegui identificar a categoria. Tente usar palavras-chave.")
            last_possible_answers = []
            last_question = ""
            last_answer_index = 0
            negative_count = 0
            continue

        possible_answers = []
        for cat in detected_cats:
            ranked = find_answers_ranked(user_input, cat_to_questions[cat], cat_to_answers[cat])
            possible_answers.extend(ranked)

        if not possible_answers:
            print("Bot: Não encontrei resposta adequada.")
            last_possible_answers = []
            last_question = ""
            last_answer_index = 0
            negative_count = 0
            continue

        print(f"Bot: {possible_answers[0]}")
        last_possible_answers = possible_answers
        last_answer_index = 0
        last_question = user_input
        negative_count = 0
