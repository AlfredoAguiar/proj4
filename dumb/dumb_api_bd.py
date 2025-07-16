import sys
import httpx
import unicodedata
import numpy as np
import faiss
from langdetect import detect
from sentence_transformers import SentenceTransformer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
import logging

# ========== Logging ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("chatbot_api")
logger.info("Logger configurado com sucesso!")

# ========== FastAPI App ==========
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== Modelo ==========
try:
    model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Modelo de embeddings carregado com sucesso.")
except Exception as e:
    logger.exception("Erro ao carregar modelo de embeddings.")
    sys.exit(1)

# ========== Estruturas de dados ==========
data_cache = {}
conversation_states = {}

# ========== Utilitários ==========
def normalize_text(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')

def detect_categories(user_input, category_keywords):
    norm_input = normalize_text(user_input)
    return [cat_id for cat_id, keywords in category_keywords.items() if any(word in norm_input for word in keywords)]

def is_negative_feedback(user_input, lang, category_keywords, feedback_ids):
    feedback_id = feedback_ids.get(lang)
    if not feedback_id:
        return False
    keywords = category_keywords.get(feedback_id, [])
    return any(k in normalize_text(user_input) for k in keywords)

# ========== Busca por Similaridade ==========
def find_answers_ruled_based(input_text, questions_by_cat, answers_by_cat, lang, detected_cats, top_k=5):
    input_embedding = model.encode([input_text], convert_to_numpy=True)
    input_embedding /= np.linalg.norm(input_embedding)

    all_questions, all_answers = [], []
    for cat_id in detected_cats:
        key = (cat_id, lang)
        all_questions.extend(questions_by_cat.get(key, []))
        all_answers.extend(answers_by_cat.get(key, []))

    if not all_questions:
        return []

    embeddings = model.encode(all_questions, convert_to_numpy=True)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)

    similarities = np.dot(embeddings, input_embedding.T).flatten()
    ranked = sorted(zip(similarities, all_questions, all_answers), key=lambda x: x[0], reverse=True)

    seen, unique_answers = set(), []
    for _, q, a in ranked:
        if q not in seen:
            seen.add(q)
            unique_answers.append(a)
        if len(unique_answers) >= top_k:
            break

    return unique_answers

def find_answers_faiss(input_text, indices_by_cat, lang, detected_cats, top_k=5):
    input_embedding = model.encode([input_text], convert_to_numpy=True)
    candidates = []

    for cat_id in detected_cats:
        key = (cat_id, lang)
        data = indices_by_cat.get(key)
        if data:
            D, I = data["index"].search(input_embedding, top_k)
            for dist, idx in zip(D[0], I[0]):
                if idx < len(data["answers"]):
                    candidates.append((dist, data["questions"][idx], data["answers"][idx]))

    candidates.sort(key=lambda x: x[0])
    seen, unique_answers = set(), []
    for _, q, a in candidates:
        if q not in seen:
            seen.add(q)
            unique_answers.append(a)
        if len(unique_answers) >= top_k:
            break

    return unique_answers

# ========== Modelos ==========
class MessageRequest(BaseModel):
    message: str
    session_id: str
    chatbot_id: str
    force_reload: bool = False

# ========== Funções de carregamento ==========
async def fetch_categories(chatbot_id: str):
    url = f"http://localhost:3004/chatbot-categoria/{int(chatbot_id)}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def fetch_faq_data(chatbot_id: int):
    categories = await fetch_categories(str(chatbot_id))
    faqs = []
    async with httpx.AsyncClient() as client:
        for cat in categories:
            cat_id = cat["categoria_id"]
            url = f"http://localhost:3004/faq-categoria/?categoria_id={cat_id}"
            response = await client.get(url)
            response.raise_for_status()
            faqs.extend(response.json())
    return faqs
def detect_language(text: str) -> str:
    try:
        if len(text) < 10:
            return "pt"
        detected = detect(text)
        if detected == "en":
            return "en"
        elif detected == "pt":
            return "pt"
        else:
            return "pt"  # fallback padrão
    except:
        return "pt"



async def fetch_no_response_message(chatbot_id: int, lang: str):
    url = f"http://localhost:3004/chatbots/{chatbot_id}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            chatbot_data = response.json()
            return chatbot_data.get(
                "mensagem_no_response_pt" if lang == "pt" else "mensagem_no_response_en",
                "Desculpe, não tenho uma resposta para isso." if lang == "pt" else "Sorry, I don't have an answer for that."
            )
    except Exception as e:
        logger.error(f"Erro ao buscar mensagem padrão: {e}")
        return "Desculpe, não consegui processar sua solicitação no momento."

# ========== Rota Principal ==========
@app.post("/chat_dumb")
async def chat(req: MessageRequest):
    logger.info(f"\n=== NOVA INTERAÇÃO ===\nChatbot: {req.chatbot_id} | Sessão: {req.session_id}\nUsuário: {req.message}")

    user_input = req.message.strip()
    if not user_input:
        return {"response": "Por favor, escreva algo."}

    lang = detect_language(user_input)

    if req.force_reload and req.chatbot_id in data_cache:
        data_cache.pop(req.chatbot_id, None)

    if req.chatbot_id not in data_cache:
        categories = await fetch_categories(req.chatbot_id)
        faqs = await fetch_faq_data(int(req.chatbot_id))

        category_keywords, feedback_ids = {}, {"pt": None, "en": None}
        questions_by_cat, answers_by_cat, indices_by_cat = {}, {}, {}

        for cat in categories:
            cat_id = cat["categoria_id"]
            raw_keywords = cat.get("categoria", {}).get("keywords", [])
            category_keywords[cat_id] = [normalize_text(k) for k in raw_keywords]
            if cat_id == 999: feedback_ids["pt"] = cat_id
            if cat_id == 998: feedback_ids["en"] = cat_id

        for item in faqs:
            cat_id = item["categoria_id"]
            faq = item.get("faq", {})
            pergunta, resposta = faq.get("pergunta", "").strip(), faq.get("resposta", "").strip()
            idioma = "pt" if normalize_text(faq.get("idioma", "pt").lower()) in ["pt", "portugues", "português"] else "en"
            key = (cat_id, idioma)
            if pergunta and resposta:
                questions_by_cat.setdefault(key, []).append(pergunta)
                answers_by_cat.setdefault(key, []).append(resposta)

        for key, questions in questions_by_cat.items():
            embeddings = model.encode(questions, convert_to_numpy=True)
            index = faiss.IndexFlatL2(embeddings.shape[1])
            index.add(embeddings)
            indices_by_cat[key] = {
                "index": index,
                "questions": questions,
                "answers": answers_by_cat[key],
            }

        data_cache[req.chatbot_id] = {
            "category_keywords": category_keywords,
            "feedback_negativo_ids": feedback_ids,
            "questions_by_category": questions_by_cat,
            "answers_by_category": answers_by_cat,
            "indices_by_category": indices_by_cat,
        }

    cache = data_cache[req.chatbot_id]
    state = conversation_states.setdefault(req.session_id, {
        "language": lang,
        "last_possible_answers": [],
        "last_answer_index": 0,
        "last_question": "",
        "negative_feedback_count": 0
    })

    if user_input != state["last_question"]:
        state["negative_feedback_count"] = 0

    if is_negative_feedback(user_input, lang, cache["category_keywords"], cache["feedback_negativo_ids"]):
        state["negative_feedback_count"] += 1
        idx = state["last_answer_index"] + 1
        if idx < len(state["last_possible_answers"]):
            state["last_answer_index"] = idx
            return {"response": state["last_possible_answers"][idx]}
        return {"response": await fetch_no_response_message(int(req.chatbot_id), lang)}

    categorias = detect_categories(user_input, cache["category_keywords"])
    if not categorias:
        return {"response": await fetch_no_response_message(int(req.chatbot_id), lang)}

    if state["negative_feedback_count"] < 2:
        answers = find_answers_ruled_based(user_input, cache["questions_by_category"], cache["answers_by_category"], lang, categorias)
    else:
        answers = find_answers_faiss(user_input, cache["indices_by_category"], lang, categorias)

    if not answers:
        return {"response": await fetch_no_response_message(int(req.chatbot_id), lang)}

    state.update({
        "last_question": user_input,
        "last_possible_answers": answers,
        "last_answer_index": 0
    })

    return {"response": answers[0]}
