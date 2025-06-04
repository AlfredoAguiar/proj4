import os
import unicodedata
from langdetect import detect

def normalize_text(text):
    text = text.lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

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

def load_qas_and_categories(bot_folder, language):
    suffix = f"_{language}"
    cat_to_questions = {}
    cat_to_answers = {}
    category_keywords = {}

    categories_path = os.path.join(bot_folder, f"categories{suffix}.txt")
    if os.path.exists(categories_path):
        with open(categories_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                cat, keys_str = line.split(":", 1)
                # Normaliza palavras-chave para facilitar matching
                category_keywords[cat.strip()] = [normalize_text(k.strip()) for k in keys_str.split(",")]

    for filename in os.listdir(bot_folder):
        if filename.endswith(f"_qa{suffix}.txt"):
            category = filename.replace(f"_qa{suffix}.txt", "")
            path = os.path.join(bot_folder, filename)
            questions, answers = load_qa_from_file(path)
            cat_to_questions[category] = questions
            cat_to_answers[category] = answers

    return category_keywords, cat_to_questions, cat_to_answers

def detect_category(user_input, category_keywords):
    normalized_input = normalize_text(user_input)
    for cat, keywords in category_keywords.items():
        for word in keywords:
            if word in normalized_input:
                return cat
    return None

def find_answers_ranked(user_input, questions, answers):
    user_norm = normalize_text(user_input)
    scored = []

    for q, a in zip(questions, answers):
        q_norm = normalize_text(q)
        # pontuação simples pela quantidade de palavras em comum
        score = sum(1 for word in q_norm.split() if word in user_norm)
        if score > 0:
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
    return any(phrase in user_norm for phrase in neg_phrases)

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

    current_language = None
    category_keywords = {}
    cat_to_questions = {}
    cat_to_answers = {}
    neg_feedback = set()
    last_possible_answers = []
    last_answer_index = 0

    print("Pode começar a escrever a sua pergunta (em português ou inglês).")
    print("Escreva 'sair' ou 'exit' para terminar.")

    while True:
        user_input = input("\nVocê: ").strip()
        if user_input.lower() in ["exit", "sair"]:
            print("Bot: Até à próxima!")
            break

        # Detecta idioma (pt ou en)
        try:
            lang = detect(user_input)
            lang = "pt" if lang == "pt" else "en"
        except:
            lang = "pt"

        # Se idioma mudou, recarrega dados
        if lang != current_language:
            current_language = lang
            category_keywords, cat_to_questions, cat_to_answers = load_qas_and_categories(bot_path, lang)
            neg_path = os.path.join(bot_path, f"negative_feedback_{lang}.txt")
            neg_feedback = load_negative_feedback(neg_path)
            print_welcome(lang, selected_bot)

        # Se for feedback negativo, responde próxima resposta
        if is_negative_feedback(user_input, neg_feedback):
            if last_possible_answers and last_answer_index + 1 < len(last_possible_answers):
                last_answer_index += 1
                print(f"Bot: {last_possible_answers[last_answer_index]}")
            else:
                if current_language == "pt":
                    print("Bot: Não tenho mais respostas possíveis para essa pergunta.")
                else:
                    print("Bot: I have no more possible answers for this question.")
            continue


        current_category = detect_category(user_input, category_keywords)

        if not current_category or current_category not in cat_to_questions:
            if current_language == "pt":
                print("Bot: Não consegui identificar a categoria. Tente usar palavras-chave ou escreva o nome do tema.")
            else:
                print("Bot: I couldn't identify the category. Please try using keywords or write the topic name.")
            last_possible_answers = []
            last_answer_index = 0
            continue

        possible_answers = find_answers_ranked(user_input, cat_to_questions[current_category],
                                               cat_to_answers[current_category])

        if not possible_answers:
            if current_language == "pt":
                print("Bot: Lamento, não encontrei nenhuma resposta adequada.")
            else:
                print("Bot: Sorry, I couldn't find any suitable answer.")
            last_possible_answers = []
            last_answer_index = 0
            continue

        last_possible_answers = possible_answers
        last_answer_index = 0
        print(f"Bot: {possible_answers[0]}")
