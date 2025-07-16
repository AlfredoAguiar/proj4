import os
import unicodedata
from langdetect import detect
from difflib import SequenceMatcher
import faiss
from sentence_transformers import SentenceTransformer
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

# ---------------- Configuração ------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bots_folder = "bots"
selected_bot = "dumb_faq"
bot_path = os.path.join(bots_folder, selected_bot)
model = SentenceTransformer("all-MiniLM-L6-v2")

data_cache = {}  # Cache por idioma
conversation_states = {}  # Estado separado por sessão/usuário

# ---------------- Utilidades ------------------

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def load_qa_from_file(path):
    questions, answers = [], []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 2:
                questions.append(parts[0])
                answers.append(parts[1])
    return questions, answers

def detect_categories(user_input, category_keywords):
    norm_input = normalize_text(user_input)
    return [cat for cat, keywords in category_keywords.items() if any(word in norm_input for word in keywords)]

def find_answers_ranked(user_input, questions, answers):
    user_norm = normalize_text(user_input)
    scored = []
    for q, a in zip(questions, answers):
        sim = similarity(normalize_text(q), user_norm)
        if sim > 0.3:
            scored.append((sim, a))
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
        if (phrase in user_norm) and (
            user_norm.startswith(phrase) or user_norm.endswith(phrase) or f" {phrase} " in f" {user_norm} "):
            return True
    return False

def load_qas_and_categories(bot_folder, language):
    suffix = f"_{language}"
    cat_to_questions, cat_to_answers, category_keywords, cat_to_index = {}, {}, {}, {}

    categories_path = os.path.join(bot_folder, f"categories{suffix}.txt")
    if os.path.exists(categories_path):
        with open(categories_path, "r", encoding="utf-8") as f:
            for line in f:
                if ":" in line:
                    cat, keys_str = line.strip().split(":", 1)
                    category_keywords[cat.strip()] = [normalize_text(k.strip()) for k in keys_str.split(",")]

    for filename in os.listdir(bot_folder):
        if filename.endswith(f"_qa{suffix}.txt"):
            cat = filename.replace(f"_qa{suffix}.txt", "")
            path = os.path.join(bot_folder, filename)
            questions, answers = load_qa_from_file(path)
            cat_to_questions[cat] = questions
            cat_to_answers[cat] = answers
            index_path = os.path.join(bot_folder, f"{cat}_qa{suffix}.index")
            if os.path.exists(index_path):
                cat_to_index[cat] = faiss.read_index(index_path)

    return category_keywords, cat_to_questions, cat_to_answers, cat_to_index


def search_faiss_answer(user_input, index, answers, top_k=3, max_distance=10.0):
    emb = model.encode([user_input]).astype('float32')
    distances, indices = index.search(emb, top_k)

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < len(answers):
            results.append((dist, answers[idx]))

    results.sort(key=lambda x: x[0])

    filtered = [a for dist, a in results if dist <= max_distance]

    return filtered


# ---------------- API ------------------

class MessageRequest(BaseModel):
    message: str
    session_id: str  # Estado por sessão

@app.post("/chat_dumb")
async def chat(req: MessageRequest):
    user_input = req.message.strip()
    session_id = req.session_id.strip()

    if not user_input:
        return {"response": "Por favor, escreva algo."}

    try:
        lang = detect(user_input) if len(user_input) >= 10 else "pt"
        lang = "pt" if lang == "pt" else "en"
    except:
        lang = "pt"

    if lang not in data_cache:
        ck, cq, ca, ci = load_qas_and_categories(bot_path, lang)
        neg_feedback = load_negative_feedback(os.path.join(bot_path, f"negative_feedback_{lang}.txt"))
        data_cache[lang] = (ck, cq, ca, ci, neg_feedback)

    category_keywords, cat_to_questions, cat_to_answers, cat_to_index, neg_feedback = data_cache[lang]

    if session_id not in conversation_states:
        conversation_states[session_id] = {
            "language": lang,
            "last_possible_answers": [],
            "last_answer_index": 0,
            "last_question": "",
            "negative_feedback_count": 0
        }

    state = conversation_states[session_id]

    if is_negative_feedback(user_input, neg_feedback):
        state["negative_feedback_count"] += 1
        if state["last_possible_answers"] and state["last_answer_index"] + 1 < len(state["last_possible_answers"]):
            state["last_answer_index"] += 1
            return {"response": state["last_possible_answers"][state["last_answer_index"]]}

        if state["negative_feedback_count"] >= 2 and state["last_question"]:
            current_categories = detect_categories(state["last_question"], category_keywords)
            for cat in current_categories:
                if cat in cat_to_index:
                    faiss_results = search_faiss_answer(state["last_question"], cat_to_index[cat], cat_to_answers[cat])
                    if faiss_results:
                        return {"response": faiss_results[0]}
            return {"response": "Não tenho mais respostas possíveis." if lang == "pt" else "No more possible answers."}

        return {"response": "Não tenho mais respostas possíveis." if lang == "pt" else "No more possible answers."}

    state.update({
        "last_question": user_input,
        "negative_feedback_count": 0,
        "last_possible_answers": [],
        "last_answer_index": 0
    })

    categories = detect_categories(user_input, category_keywords)

    if not categories:
        msg = "Não consegui identificar uma categoria para sua pergunta. Tente reformular." if lang == "pt" else "Couldn't identify a category for your question. Please rephrase."
        return {"response": msg}

    possible_answers = []
    for cat in categories:
        if cat in cat_to_questions:
            ranked = find_answers_ranked(user_input, cat_to_questions[cat], cat_to_answers[cat])
            possible_answers.extend(ranked)
        if cat in cat_to_index:
            faiss_results = search_faiss_answer(user_input, cat_to_index[cat], cat_to_answers[cat], top_k=3,
                                                max_distance=10.0)
            possible_answers.extend(faiss_results)

    # Remover duplicados mantendo ordem
    unique_answers = []
    seen = set()
    for ans in possible_answers:
        if ans not in seen:
            seen.add(ans)
            unique_answers.append(ans)

    if not unique_answers:
        msg = "Lamento, não encontrei resposta adequada." if lang == "pt" else "Sorry, I couldn't find a suitable answer."
        return {"response": msg}

    state["last_possible_answers"] = unique_answers
    state["last_answer_index"] = 0

    return {"response": unique_answers[0]}
