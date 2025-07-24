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

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("dumb_api_bd")
logger.info("Logger configurado e pronto!")

# App & CORS
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Embeddings
model = SentenceTransformer("all-MiniLM-L6-v2")
data_cache = {}
conversation_states = {}

# Utils
import re

def normalize_text(text):
    text = unicodedata.normalize('NFD', text.lower())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^\w\s]', '', text).strip()

def detect_categories(user_input, category_keywords):
    norm_input = normalize_text(user_input)
    return [cat_id for cat_id, keywords in category_keywords.items() if any(word in norm_input for word in keywords)]

def is_feedback_negativo(user_input, lang, category_keywords, feedback_negativo_ids):
    id_feedback = feedback_negativo_ids.get(lang)
    if id_feedback is None:
        return False
    norm_input = normalize_text(user_input)
    keywords = category_keywords.get(id_feedback, [])
    return any(k in norm_input for k in keywords)

def detect_language(text: str) -> str:
    try:
        from langdetect import detect
        norm = normalize_text(text)

        greetings_en = {
            "hi", "hello", "hey", "good morning", "good afternoon",
            "good evening", "howdy", "greetings", "what's up", "yo", "sup"
        }

        greetings_pt = {
            "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite",
            "alô", "alo", "e aí", "fala", "boas"
        }

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
    greetings_pt = {
        "ola", "olá", "bom dia", "boa tarde", "boa noite", "oi",
        "alô", "alo", "hey", "boas", "e aí", "fala", "opa", "tudo bem", "beleza"
    }

    greetings_en = {
        "hello", "hi", "good morning", "good afternoon", "good evening",
        "hey", "howdy", "greetings", "what's up", "yo", "sup", "hiya"
    }

    norm_text = normalize_text(text.strip())
    lang = detect_language(text)

    greetings = greetings_en if lang == "en" else greetings_pt

    # Se for só uma saudação curta, como "olá" ou "hi"
    if norm_text in greetings:
        return True

    # Se for frase longa, ignorar como saudação
    if len(norm_text.split()) > 3:
        return False

    # Última tentativa: começa com saudação?
    for greet in greetings:
        if norm_text.startswith(greet):
            return True

    return False


def find_answers_faiss_with_threshold(user_input, indices_by_category, lang, categorias_detectadas, top_k=5, threshold=0.6):
    input_embedding = model.encode([user_input], convert_to_numpy=True)
    input_embedding /= np.linalg.norm(input_embedding)

    all_candidates = []
    for cat_id in categorias_detectadas:
        key = (cat_id, lang)
        data = indices_by_category.get(key)
        if data:
            D, I = data["index"].search(input_embedding, top_k)
            for dist, idx in zip(D[0], I[0]):
                if idx < len(data["answers"]):
                    similarity = 1 - dist / 2
                    all_candidates.append((similarity, data["questions"][idx], data["answers"][idx]))

    all_candidates.sort(key=lambda x: x[0], reverse=True)
    seen = set()
    answers = []
    for sim, q, a in all_candidates:
        if sim < threshold:
            continue
        if q not in seen:
            seen.add(q)
            answers.append(a)
    return answers

class MessageRequest(BaseModel):
    message: str
    session_id: str
    chatbot_id: str
    force_reload: bool = False

async def fetch_categories(chatbot_id: str):
    url = f"http://localhost:3004/chatbot-categoria/{int(chatbot_id)}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        res.raise_for_status()
        return res.json()

async def fetch_faq_data(chatbot_id: int):
    categories = await fetch_categories(str(chatbot_id))
    faqs = []
    async with httpx.AsyncClient() as client:
        for cat in categories:
            cat_id = cat["categoria_id"]
            url = f"http://localhost:3004/faq-categoria/?categoria_id={cat_id}"
            res = await client.get(url)
            res.raise_for_status()
            faqs.extend(res.json())
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

@app.post("/chat_dumb")
async def chat(req: MessageRequest):
    user_input = req.message.strip()
    lang = detect_language(user_input)
    chatbot_id = req.chatbot_id.strip()
    session_id = req.session_id.strip()

    if req.force_reload and chatbot_id in data_cache:
        del data_cache[chatbot_id]

    if chatbot_id not in data_cache:
        categories = await fetch_categories(chatbot_id)
        faqs = await fetch_faq_data(int(chatbot_id))

        cat_keywords, feedback_ids = {}, {"pt": None, "en": None}
        questions, answers, indices = {}, {}, {}

        for cat in categories:
            cat_id = cat["categoria_id"]
            keys = cat.get("categoria", {}).get("keywords", [])
            cat_keywords[cat_id] = [normalize_text(k) for k in keys]
            if cat_id == 999: feedback_ids["pt"] = cat_id
            if cat_id == 998: feedback_ids["en"] = cat_id

        for item in faqs:
            cat_id = item["categoria_id"]
            faq = item.get("faq", {})
            q = faq.get("pergunta", "").strip()
            a = faq.get("resposta", "").strip()
            idioma = "pt" if normalize_text(faq.get("idioma", "pt").lower()) in ["pt", "portugues", "português"] else "en"
            key = (cat_id, idioma)
            if q and a:
                questions.setdefault(key, []).append(q)
                answers.setdefault(key, []).append(a)

        for key, qlist in questions.items():
            embeds = model.encode(qlist, convert_to_numpy=True)
            embeds /= np.linalg.norm(embeds, axis=1, keepdims=True)
            idx = faiss.IndexFlatL2(embeds.shape[1])
            idx.add(embeds)
            indices[key] = {"index": idx, "questions": qlist, "answers": answers[key]}

        data_cache[chatbot_id] = {
            "category_keywords": cat_keywords,
            "feedback_negativo_ids": feedback_ids,
            "indices_by_category": indices
        }

    cache = data_cache[chatbot_id]
    state = conversation_states.setdefault(session_id, {
        "language": lang,
        "last_possible_answers": [],
        "last_answer_index": 0,
        "last_question": "",
        "negative_feedback_count": 0
    })

    if is_greeting(user_input):
        return {"response": await fetch_greeting_message(int(chatbot_id), lang)}

    if is_feedback_negativo(user_input, lang, cache["category_keywords"], cache["feedback_negativo_ids"]):
        idx = state["last_answer_index"] + 1
        if idx < len(state["last_possible_answers"]):
            state["last_answer_index"] = idx
            return {"response": state["last_possible_answers"][idx]}
        return {"response": await fetch_no_response_message(int(chatbot_id), lang)}

    categorias = detect_categories(user_input, cache["category_keywords"])
    if not categorias:
        return {"response": await fetch_no_response_message(int(chatbot_id), lang)}

    answers = find_answers_faiss_with_threshold(user_input, cache["indices_by_category"], lang, categorias)
    if not answers:
        return {"response": await fetch_no_response_message(int(chatbot_id), lang)}

    state.update({
        "last_question": user_input,
        "last_possible_answers": answers,
        "last_answer_index": 0
    })

    return {"response": answers[0]}
