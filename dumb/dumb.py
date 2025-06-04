import os
import unicodedata

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

def load_qas_and_categories(bot_folder):
    """
    Espera:
      - arquivos *_qa.txt com perguntas e respostas
      - arquivo categories.txt com definição das categorias e suas palavras-chave no formato:
          categoria: palavra1, palavra2, palavra3
    """
    cat_to_questions = {}
    cat_to_answers = {}
    category_keywords = {}

    categories_path = os.path.join(bot_folder, "categories.txt")
    if os.path.exists(categories_path):
        with open(categories_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                cat, keys_str = line.split(":", 1)
                category_keywords[cat.strip()] = [k.strip() for k in keys_str.split(",")]

    for filename in os.listdir(bot_folder):
        if filename.endswith("_qa.txt"):
            category = filename.replace("_qa.txt", "")
            path = os.path.join(bot_folder, filename)
            questions, answers = load_qa_from_file(path)
            cat_to_questions[category] = questions
            cat_to_answers[category] = answers

    return category_keywords, cat_to_questions, cat_to_answers

def detect_category(user_input, category_keywords):
    normalized_input = normalize_text(user_input)
    for cat, keywords in category_keywords.items():
        for word in keywords:
            normalized_word = normalize_text(word)
            if normalized_word in normalized_input:
                return cat
    return None

def find_answers_ranked(user_input, questions, answers):
    user_norm = normalize_text(user_input)
    scored = []

    for q, a in zip(questions, answers):
        q_norm = normalize_text(q)
        score = sum(1 for word in q_norm.split() if word in user_norm)
        if score > 0:
            scored.append((score, a))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored]

def is_negative_feedback(user_input):
    neg_keywords = {
        "não", "nao", "não é isso", "nao é isso", "outra", "outra resposta",
        "não gostei", "nao gostei", "errado", "incorreto"
    }
    user_norm = normalize_text(user_input).strip()
    words = user_norm.split()

    if len(words) <= 3:
        for phrase in neg_keywords:
            if phrase == user_norm or phrase in user_norm:
                return True
    return False

def print_welcome(language, bot_name):
    if language == "pt":
        print(f"Olá! Você está conversando com o bot '{bot_name}'. Pergunte sobre os assuntos disponíveis.")
        print("Digite 'exit' para sair.")

    else:
        print(f"Hello! You are chatting with bot '{bot_name}'. Ask about the available topics.")
        print("Type 'exit' to quit.")


def list_bots(bots_folder):
    # Lista as pastas dentro do bots_folder
    return [d for d in os.listdir(bots_folder) if os.path.isdir(os.path.join(bots_folder, d))]

if __name__ == "__main__":
    bots_folder = "bots"  # pasta onde estão os bots (cada um em uma subpasta)

    # Seleção de idioma
    while True:
        lang = input("Escolha o idioma / Choose language (pt/en): ").strip().lower()
        if lang in ["pt", "en"]:
            break
        print("Idioma inválido. / Invalid language.")

    # Listar bots disponíveis
    bots = list_bots(bots_folder)
    if not bots:
        print("Nenhum bot encontrado na pasta 'bots'.")
        exit()

    print("Bots disponíveis:" if lang == "pt" else "Available bots:")
    for i, bot_name in enumerate(bots, 1):
        print(f"{i}. {bot_name}")

    while True:
        choice = input("Escolha um bot pelo número / Choose a bot by number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(bots):
            selected_bot = bots[int(choice) - 1]
            break
        print("Escolha inválida. / Invalid choice.")

    # Carregar categorias e QA do bot selecionado
    bot_path = os.path.join(bots_folder, selected_bot)
    category_keywords, cat_to_questions, cat_to_answers = load_qas_and_categories(bot_path)

    print_welcome(lang, selected_bot)

    current_category = None
    last_possible_answers = []
    last_answer_index = 0

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() == "exit":
            print("Bot: Até logo!" if lang == "pt" else "Bot: Goodbye!")
            break

        user_input_lower = user_input.lower()

        if user_input_lower in cat_to_questions.keys():
            current_category = user_input_lower
            last_possible_answers = []
            last_answer_index = 0
            if lang == "pt":
                print(f"Bot: Categoria alterada para '{current_category}'. Faça sua pergunta.")
            else:
                print(f"Bot: Category changed to '{current_category}'. Ask your question.")
            continue

        # Se feedback negativo, mostrar próxima resposta
        if is_negative_feedback(user_input):
            if last_possible_answers and last_answer_index + 1 < len(last_possible_answers):
                last_answer_index += 1
                print(f"Bot: {last_possible_answers[last_answer_index]}")
            else:
                if lang == "pt":
                    print("Bot: Não tenho outras respostas para essa pergunta.")
                else:
                    print("Bot: I have no other answers for that question.")
            continue

        # Detectar categoria se não definida
        if not current_category:
            current_category = detect_category(user_input, category_keywords)

        if not current_category or current_category not in cat_to_questions:
            if lang == "pt":
                print("Bot: Não consegui detectar a categoria. Tente usar palavras-chave ou digite o nome da categoria.")
            else:
                print("Bot: Couldn't detect category. Try keywords or type the category name.")
            last_possible_answers = []
            last_answer_index = 0
            current_category = None
            continue

        # Buscar respostas
        possible_answers = find_answers_ranked(user_input, cat_to_questions[current_category], cat_to_answers[current_category])

        if not possible_answers:
            if lang == "pt":
                print("Bot: Desculpe, não encontrei resposta adequada.")
            else:
                print("Bot: Sorry, no suitable answer found.")
            last_possible_answers = []
            last_answer_index = 0
            continue

        last_possible_answers = possible_answers
        last_answer_index = 0

        print(f"Bot: {possible_answers[0]}")


