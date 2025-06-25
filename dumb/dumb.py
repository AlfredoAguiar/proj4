import os
import unicodedata
from langdetect import detect
from difflib import SequenceMatcher
import random
import faiss
from sentence_transformers import SentenceTransformer


def normalize_text(text):
    text = text.lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def load_qa_from_file(path):
    questions = []
    answers = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) != 2:
                print(f"[AVISO] Linha inválida ignorada no arquivo {path}: {line.strip()}")
                continue
            questions.append(parts[0])
            answers.append(parts[1])
    return questions, answers


def detect_category(user_input, category_keywords):
    normalized_input = normalize_text(user_input)
    for cat, keywords in category_keywords.items():
        for word in keywords:
            if word in normalized_input:
                return cat
    return None

def detect_categories(user_input, category_keywords):
    normalized_input = normalize_text(user_input)
    detected = []
    for cat, keywords in category_keywords.items():
        for word in keywords:
            if word in normalized_input:
                detected.append(cat)
                break  # Evita repetição se já detectou a categoria
    return detected

def find_answers_ranked(user_input, questions, answers):
    user_norm = normalize_text(user_input)
    scored = []

    for q, a in zip(questions, answers):
        q_norm = normalize_text(q)
        score = similarity(q_norm, user_norm)
        if score > 0.3:
            scored.append((score, a))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored]

def load_negative_feedback(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return set(normalize_text(line.strip()) for line in f if line.strip())

def is_negative_feedback(user_input, neg_phrases):
    user_norm = normalize_text(user_input)
    for phrase in neg_phrases:
        if phrase in user_norm:
            # Garante que a frase esteja isolada ou no início/fim, evita falsos positivos
            if f" {phrase} " in f" {user_norm} " or user_norm.startswith(phrase) or user_norm.endswith(phrase):
                return True
    return False

def print_welcome(language, bot_name):
    if language == "pt":
        print(f"Olá! Está a conversar com o assistente '{bot_name}'.")
        print("Pode fazer perguntas sobre os temas disponíveis.")
        print("Escreva 'sair' para terminar a conversa.")
    else:
        print(f"Hello! You are chatting with bot '{bot_name}'.")
        print("Ask about the available topics.")
        print("Type 'exit' to quit.")

def list_bots(bots_folder):
    return [d for d in os.listdir(bots_folder) if os.path.isdir(os.path.join(bots_folder, d))]


def load_qas_and_categories(bot_folder, language):
    suffix = f"_{language}"
    cat_to_questions = {}
    cat_to_answers = {}
    category_keywords = {}
    cat_to_index = {}

    categories_path = os.path.join(bot_folder, f"categories{suffix}.txt")
    if os.path.exists(categories_path):
        with open(categories_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                cat, keys_str = line.split(":", 1)
                category_keywords[cat.strip()] = [normalize_text(k.strip()) for k in keys_str.split(",")]

    for filename in os.listdir(bot_folder):
        if filename.endswith(f"_qa{suffix}.txt"):
            category = filename.replace(f"_qa{suffix}.txt", "")
            path = os.path.join(bot_folder, filename)
            questions, answers = load_qa_from_file(path)
            cat_to_questions[category] = questions
            cat_to_answers[category] = answers

            # Tenta carregar FAISS
            index_path = os.path.join(bot_folder, f"{category}.index")
            if os.path.exists(index_path):
                index = faiss.read_index(index_path)
                cat_to_index[category] = index

    return category_keywords, cat_to_questions, cat_to_answers, cat_to_index

def search_faiss_answer(user_input, index, questions, answers, model, top_k=3):
    user_emb = model.encode([user_input]).astype('float32')
    distances, indices = index.search(user_emb, top_k)
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < len(answers):
            results.append((dist, answers[idx]))
    results.sort(key=lambda x: x[0])  # Menor distância é melhor
    return [a for _, a in results]

# ---------------------- Loop Principal -----------------------

if __name__ == "__main__":
    bots_folder = "bots"
    bots = list_bots(bots_folder)
    if not bots:
        print("Não foram encontrados bots na pasta 'bots'.")
        exit()

    print("Bots disponíveis:")
    for i, bot_name in enumerate(bots, 1):
        print(f"{i}. {bot_name}")

    while True:
        choice = input("Escolha um bot pelo número: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(bots):
            selected_bot = bots[int(choice) - 1]
            break
        print("Escolha inválida.")

    bot_path = os.path.join(bots_folder, selected_bot)
    model = SentenceTransformer("all-MiniLM-L6-v2")

    current_language = None
    data_cache = {}
    last_possible_answers = []
    last_answer_index = 0
    last_question = ""
    negative_feedback_count = 0

    print("Pode começar a escrever a sua pergunta (em português ou inglês).")
    print("Escreva 'sair' ou 'exit' para terminar.")

    while True:
        user_input = input("\nVocê: ").strip()
        if user_input.lower() in ["exit", "sair"]:
            print("Bot: Até à próxima!")
            break

        try:
            lang = detect(user_input)
            lang = "pt" if lang == "pt" else "en"
        except:
            lang = "pt"

        if lang != current_language:
            current_language = lang
            if lang not in data_cache:
                category_keywords, cat_to_questions, cat_to_answers, cat_to_index = load_qas_and_categories(bot_path, lang)
                neg_path = os.path.join(bot_path, f"negative_feedback_{lang}.txt")
                neg_feedback = load_negative_feedback(neg_path)
                data_cache[lang] = (category_keywords, cat_to_questions, cat_to_answers, cat_to_index, neg_feedback)
            category_keywords, cat_to_questions, cat_to_answers, cat_to_index, neg_feedback = data_cache[lang]
            print_welcome(lang, selected_bot)

        if is_negative_feedback(user_input, neg_feedback):
            negative_feedback_count += 1
            if last_possible_answers and last_answer_index + 1 < len(last_possible_answers):
                last_answer_index += 1
                print(f"Bot: {last_possible_answers[last_answer_index]}")
            elif negative_feedback_count >= 2 and last_question:
                current_categories = detect_categories(last_question, category_keywords)
                found_answer = False
                for cat in current_categories:
                    if cat in cat_to_index:
                        faiss_results = search_faiss_answer(last_question, cat_to_index[cat], cat_to_questions[cat], cat_to_answers[cat], model)
                        if faiss_results:
                            print(f"Bot (IA): {faiss_results[0]}")
                            found_answer = True
                            break
                if not found_answer:
                    msg = "Não tenho mais respostas possíveis." if current_language == "pt" else "I have no more possible answers."
                    print(f"Bot: {msg}")
            else:
                msg = "Não tenho mais respostas possíveis." if current_language == "pt" else "I have no more possible answers."
                print(f"Bot: {msg}")
            continue

        negative_feedback_count = 0
        last_question = user_input
        current_categories = detect_categories(user_input, category_keywords)

        if not current_categories:
            available_cats = ", ".join(category_keywords.keys())
            if current_language == "pt":
                print(f"Bot: Não consegui identificar categorias. Tente usar palavras-chave. Categorias: {available_cats}")
            else:
                print(f"Bot: Couldn't identify categories. Try using keywords. Categories: {available_cats}")
            last_possible_answers = []
            last_answer_index = 0
            continue

        possible_answers = []
        for cat in current_categories:
            if cat in cat_to_questions:
                ranked_answers = find_answers_ranked(user_input, cat_to_questions[cat], cat_to_answers[cat])
                possible_answers.extend(ranked_answers)

        if not possible_answers:
            msg = "Lamento, não encontrei nenhuma resposta adequada." if current_language == "pt" else "Sorry, I couldn't find a suitable answer."
            print(f"Bot: {msg}")
            last_possible_answers = []
            last_answer_index = 0
            continue

        possible_answers = sorted(set(possible_answers), key=lambda x: possible_answers.index(x))
        last_possible_answers = possible_answers
        last_answer_index = 0
        print(f"Bot: {possible_answers[0]}")

        for cat in current_categories:
            examples = cat_to_questions.get(cat, [])
            if examples:
                suggestions = random.sample(examples, min(3, len(examples)))
                if current_language == "pt":
                    print(f"Sugestões do tema '{cat}':")
                else:
                    print(f"Suggestions from topic '{cat}':")
                for q in suggestions:
                    print(f"- {q}")
