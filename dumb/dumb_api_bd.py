from fastapi import FastAPI
import httpx
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import numpy as np
import unicodedata
import sys
import logging
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
import re

# ========== Logging ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("chatbot_api")

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
model = SentenceTransformer("all-MiniLM-L6-v2")

# ========== Dados ==========
data_cache = {}
conversation_states = {}

# ========== Utils ==========
def normalize_text(text):
    text = unicodedata.normalize('NFD', text.lower())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^\w\s]', '', text).strip()

def detect_language(text: str) -> str:
    try:
        from langdetect import detect
        norm = normalize_text(text)

        greetings_en = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "howdy", "greetings", "what's up", "yo", "sup"}
        greetings_pt = {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "alô", "alo", "e aí", "fala", "boas"}

        if norm in greetings_en:
            return "en"
        if norm in greetings_pt:
            return "pt"

        if len(text) < 10:
            return "pt"

        detected = detect(text)
        return "en" if detected == "en" else "pt"
    except:
        return "pt"

def is_greeting(text: str) -> bool:
    greetings_pt = {"ola", "olá", "bom dia", "boa tarde", "boa noite", "oi", "alô", "alo", "hey", "boas", "e aí", "fala", "opa", "tudo bem", "beleza"}
    greetings_en = {"hello", "hi", "good morning", "good afternoon", "good evening", "hey", "howdy", "greetings", "what's up", "yo", "sup", "hiya"}
    norm_text = normalize_text(text.strip())
    lang = detect_language(text)
    greetings = greetings_en if lang == "en" else greetings_pt
    if norm_text in greetings:
        return True
    if len(norm_text.split()) > 3:
        return False
    for greet in greetings:
        if norm_text.startswith(greet):
            return True
    return False

def detect_categories(user_input, category_keywords):
    norm_input = normalize_text(user_input)
    return [cat_id for cat_id, keywords in category_keywords.items() if any(word in norm_input for word in keywords)]

def is_negative_feedback(user_input, lang, category_keywords, feedback_ids):
    feedback_id = feedback_ids.get(lang)
    if not feedback_id:
        return False
    keywords = category_keywords.get(feedback_id, [])
    return any(k in normalize_text(user_input) for k in keywords)

async def find_answers_ruled_based(input_text, questions_by_cat, answers_by_cat, embeddings_by_cat, lang, detected_cats, top_k=5):
    input_embedding = await run_in_threadpool(lambda: model.encode([input_text], convert_to_numpy=True))
    input_embedding /= np.linalg.norm(input_embedding)

    all_questions, all_answers, all_embeddings = [], [], []
    for cat_id in detected_cats:
        key = (cat_id, lang)
        all_questions.extend(questions_by_cat.get(key, []))
        all_answers.extend(answers_by_cat.get(key, []))
        emb = embeddings_by_cat.get(key)
        if emb is not None:
            all_embeddings.append(emb)

    if not all_embeddings:
        return [], 0.0

    embeddings = np.vstack(all_embeddings)
    similarities = np.dot(embeddings, input_embedding.T).flatten()
    if not len(similarities):
        return [], 0.0

    top_k_idx = np.argsort(-similarities)[:top_k]
    best_similarity = similarities[top_k_idx[0]]
    unique_answers = [all_answers[i] for i in top_k_idx]

    return unique_answers, best_similarity

# ========== Fetchers ==========
async def fetch_categories(chatbot_id: str):
    url = f"http://localhost:3004/chatbot-categoria/{int(chatbot_id)}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def fetch_faq_data(chatbot_id: int):
    categories = await fetch_categories(str(chatbot_id))

    async def fetch_cat(cat_id):
        url = f"http://localhost:3004/faq-categoria/?categoria_id={cat_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    tasks = [fetch_cat(cat["categoria_id"]) for cat in categories]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    faqs = []
    for r in results:
        if isinstance(r, list):
            faqs.extend(r)
    return faqs

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

async def fetch_greeting_message(chatbot_id: int, lang: str):
    url = f"http://localhost:3004/chatbots/{chatbot_id}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            chatbot_data = response.json()
            return chatbot_data.get(
                "mensagem_inicial_pt" if lang == "pt" else "mensagem_inicial_en",
                "Olá! Como posso ajudar?" if lang == "pt" else "Hello! How can I help you?"
            )
    except Exception as e:
        logger.error(f"Erro ao buscar mensagem de saudação: {e}")
        return "Olá! Como posso ajudar?" if lang == "pt" else "Hello! How can I help you?"

# ========== Models ==========
class MessageRequest(BaseModel):
    message: str
    session_id: str
    chatbot_id: str
    force_reload: bool = False

# ========== Rota ==========
@app.post("/chat_dumb")
async def chat(req: MessageRequest):
    logger.info(f"Chatbot: {req.chatbot_id} | Sessão: {req.session_id} | Mensagem: {req.message}")
    user_input = req.message.strip()
    if not user_input:
        return {"response": "Por favor, escreva algo."}

    lang = detect_language(user_input)

    if req.force_reload:
        data_cache.pop(req.chatbot_id, None)

    if req.chatbot_id not in data_cache:
        categories = await fetch_categories(req.chatbot_id)
        faqs = await fetch_faq_data(int(req.chatbot_id))

        category_keywords, feedback_ids = {}, {"pt": None, "en": None}
        questions_by_cat, answers_by_cat = {}, {}
        question_embeddings_by_cat = {}

        for cat in categories:
            cat_id = cat["categoria_id"]
            raw_keywords = cat.get("categoria", {}).get("keywords", [])
            category_keywords[cat_id] = [normalize_text(k) for k in raw_keywords]
            if cat_id == 999: feedback_ids["pt"] = cat_id
            if cat_id == 998: feedback_ids["en"] = cat_id

        for item in faqs:
            cat_id = item["categoria_id"]
            faq = item.get("faq", {})
            pergunta = faq.get("pergunta", "").strip()
            resposta = faq.get("resposta", "").strip()
            idioma = "pt" if normalize_text(faq.get("idioma", "pt").lower()) in ["pt", "portugues", "português"] else "en"
            key = (cat_id, idioma)
            if pergunta and resposta:
                questions_by_cat.setdefault(key, []).append(pergunta)
                answers_by_cat.setdefault(key, []).append(resposta)

        for key, questions in questions_by_cat.items():
            embeddings = await run_in_threadpool(lambda q=questions: model.encode(q, convert_to_numpy=True))
            embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
            question_embeddings_by_cat[key] = embeddings

        data_cache[req.chatbot_id] = {
            "category_keywords": category_keywords,
            "feedback_negativo_ids": feedback_ids,
            "questions_by_category": questions_by_cat,
            "answers_by_category": answers_by_cat,
            "question_embeddings_by_category": question_embeddings_by_cat
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

    if is_greeting(user_input):
        greeting_message = await fetch_greeting_message(int(req.chatbot_id), lang)
        return {"response": greeting_message}

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

    answers, similarity = await find_answers_ruled_based(
        user_input,
        cache["questions_by_category"],
        cache["answers_by_category"],
        cache["question_embeddings_by_category"],
        lang,
        categorias
    )

    SIMILARITY_THRESHOLD = 0.65
    if not answers or similarity < SIMILARITY_THRESHOLD:
        return {"response": await fetch_no_response_message(int(req.chatbot_id), lang)}

    state.update({
        "last_question": user_input,
        "last_possible_answers": answers,
        "last_answer_index": 0
    })

    return {"response": answers[0]}
