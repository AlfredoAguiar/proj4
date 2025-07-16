import os
import unicodedata
from difflib import SequenceMatcher
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

BOTS_FOLDER = "bots"
SELECTED_BOT = "dumb_faq"
BOT_PATH = os.path.join(BOTS_FOLDER, SELECTED_BOT)

DATA_CACHE = {}

def normalize_text(text):
    text = text.lower()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def load_rule_data(language):
    suffix = f"_{language}"
    cat_to_questions = {}
    cat_to_answers = {}
    category_keywords = {}

    categories_path = os.path.join(BOT_PATH, f"categories{suffix}.txt")
    if os.path.exists(categories_path):
        with open(categories_path, "r", encoding="utf-8") as f:
            for line in f:
                if ":" in line:
                    cat, keys_str = line.strip().split(":", 1)
                    category_keywords[cat.strip()] = [normalize_text(k.strip()) for k in keys_str.split(",")]

    for filename in os.listdir(BOT_PATH):
        if filename.endswith(f"_qa{suffix}.txt"):
            category = filename.replace(f"_qa{suffix}.txt", "")
            questions, answers = [], []
            with open(os.path.join(BOT_PATH, filename), "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) == 2:
                        questions.append(parts[0])
                        answers.append(parts[1])
            cat_to_questions[category] = questions
            cat_to_answers[category] = answers

    return category_keywords, cat_to_questions, cat_to_answers

def detect_categories(user_input, category_keywords):
    normalized_input = normalize_text(user_input)
    detected = []
    for cat, keywords in category_keywords.items():
        for word in keywords:
            if word in normalized_input:
                detected.append(cat)
                break
    return detected

class MessageRequest(BaseModel):
    message: str

@app.post("/chat-rule")
async def chat_rule(req: MessageRequest):
    user_input = req.message.strip()

    lang = "pt"
    try:
        from langdetect import detect
        lang = "pt" if detect(user_input) == "pt" else "en"
    except:
        pass

    if lang not in DATA_CACHE:
        DATA_CACHE[lang] = load_rule_data(lang)

    category_keywords, cat_to_questions, cat_to_answers = DATA_CACHE[lang]

    categories = detect_categories(user_input, category_keywords)
    if not categories:
        return {"response": "Não consegui identificar categorias. Tente usar palavras-chave."}

    user_norm = normalize_text(user_input)
    for cat in categories:
        questions = cat_to_questions.get(cat, [])
        answers = cat_to_answers.get(cat, [])
        scored = []
        for q, a in zip(questions, answers):
            q_norm = normalize_text(q)
            score = similarity(q_norm, user_norm)
            if score > 0.3:
                scored.append((score, a))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            return {"response": scored[0][1]}

    return {"response": "Lamento, não encontrei nenhuma resposta adequada."}
