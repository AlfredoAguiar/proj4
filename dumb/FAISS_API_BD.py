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

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("dumb_api_bd")
logger.info("Logger configurado e pronto!")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = SentenceTransformer("all-MiniLM-L6-v2")
data_cache = {}
conversation_states = {}

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')

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

def find_answers_faiss(user_input, indices_by_category, lang, categorias_detectadas, top_k=5):
    input_embedding = model.encode([user_input], convert_to_numpy=True)
    all_candidates = []

    for cat_id in categorias_detectadas:
        key = (cat_id, lang)
        data = indices_by_category.get(key)
        if data:
            index = data["index"]
            questions = data["questions"]
            answers = data["answers"]
            D, I = index.search(input_embedding, top_k)

            for dist, idx in zip(D[0], I[0]):
                if idx < len(answers):
                    pergunta = questions[idx]
                    resposta = answers[idx]
                    all_candidates.append((dist, pergunta, resposta))

    # Ordenar globalmente por menor distância
    all_candidates.sort(key=lambda x: x[0])

    seen = set()
    unique_answers = []
    for dist, pergunta, resposta in all_candidates:
        if pergunta not in seen:
            seen.add(pergunta)
            unique_answers.append(resposta)

    return unique_answers

class MessageRequest(BaseModel):
    message: str
    session_id: str
    chatbot_id: str
    force_reload: bool = False

async def fetch_categories(chatbot_id: str):
    url = f"http://localhost:3004/chatbot-categoria/{int(chatbot_id)}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Erro ao buscar categorias: {response.text}")
        return response.json()

async def fetch_faq_data(chatbot_id: int):
    categories = await fetch_categories(str(chatbot_id))
    faqs = []
    async with httpx.AsyncClient() as client:
        for cat in categories:
            categoria_id = cat["categoria_id"]
            url = f"http://localhost:3004/faq-categoria/?categoria_id={categoria_id}"
            response = await client.get(url)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Erro ao buscar FAQs para categoria {categoria_id}: {response.text}")
            faqs.extend(response.json())
    return faqs

@app.post("/chat_dumb")
async def chat(req: MessageRequest):
    logger.info("=== NOVA INTERAÇÃO ===")
    logger.info(f"Chatbot ID: {req.chatbot_id}")
    logger.info(f"Session ID: {req.session_id}")
    logger.info(f"Mensagem do usuário: {req.message}")
    user_input = req.message.strip()
    session_id = req.session_id.strip()
    chatbot_id = req.chatbot_id.strip()

    if not user_input:
        return {"response": "Por favor, escreva algo."}

    lang = detect_language(user_input)

    if req.force_reload and chatbot_id in data_cache:
        del data_cache[chatbot_id]

    if chatbot_id not in data_cache:
        categories = await fetch_categories(chatbot_id)
        faqs = await fetch_faq_data(int(chatbot_id))

        category_keywords = {}
        feedback_negativo_ids = {"pt": None, "en": None}
        for cat in categories:
            cat_id = cat["categoria_id"]
            keywords_raw = cat.get("categoria", {}).get("keywords", [])
            category_keywords[cat_id] = [normalize_text(k.strip()) for k in keywords_raw]
            if cat_id == 999:
                feedback_negativo_ids["pt"] = cat_id
            elif cat_id == 998:
                feedback_negativo_ids["en"] = cat_id

        questions_by_category = {}
        answers_by_category = {}
        indices_by_category = {}

        for item in faqs:
            cat_id = item["categoria_id"]
            faq = item.get("faq", {})
            pergunta = faq.get("pergunta", "").strip()
            resposta = faq.get("resposta", "").strip()
            idioma_raw = faq.get("idioma", "PT")
            idioma = "pt" if normalize_text(idioma_raw.strip().lower()) in ["pt", "portugues", "português"] else "en"

            key = (cat_id, idioma)
            if not pergunta or not resposta:
                continue

            if key not in questions_by_category:
                questions_by_category[key] = []
                answers_by_category[key] = []

            questions_by_category[key].append(pergunta)
            answers_by_category[key].append(resposta)

        for key, questions in questions_by_category.items():
            embeddings = model.encode(questions, convert_to_numpy=True)
            dim = embeddings.shape[1]
            index = faiss.IndexFlatL2(dim)
            index.add(embeddings)
            indices_by_category[key] = {
                "index": index,
                "questions": questions,
                "answers": answers_by_category[key],
                "embeddings": embeddings,
            }

        data_cache[chatbot_id] = {
            "category_keywords": category_keywords,
            "feedback_negativo_ids": feedback_negativo_ids,
            "indices_by_category": indices_by_category
        }

    cache = data_cache[chatbot_id]
    category_keywords = cache["category_keywords"]
    feedback_negativo_ids = cache["feedback_negativo_ids"]
    indices_by_category = cache["indices_by_category"]

    if session_id not in conversation_states:
        conversation_states[session_id] = {
            "language": lang,
            "last_possible_answers": [],
            "last_answer_index": 0,
            "last_question": "",
            "negative_feedback_count": 0
        }

    state = conversation_states[session_id]

    # Verifica feedback negativo
    if is_feedback_negativo(user_input, lang, category_keywords, feedback_negativo_ids):
        previous_answers = state.get("last_possible_answers", [])
        index = state.get("last_answer_index", 0) + 1
        if index < len(previous_answers):
            state["last_answer_index"] = index
            logger.info(f"🔁 Feedback negativo detectado. Próxima resposta: {previous_answers[index][:150]}...")
            return {"response": previous_answers[index]}
        else:
            msg = "Lamento, não tenho mais respostas alternativas." if lang == "pt" else "Sorry, I don't have more alternative answers."
            logger.info("🚫 Nenhuma resposta alternativa disponível.")
            return {"response": msg}

    # Reset do estado
    state.update({
        "last_question": user_input,
        "negative_feedback_count": 0,
        "last_possible_answers": [],
        "last_answer_index": 0
    })

    categorias_detectadas = detect_categories(user_input, category_keywords)
    logger.info(f"Categorias detectadas: {categorias_detectadas}")

    if not categorias_detectadas:
        msg = "Não consegui identificar uma categoria para sua pergunta. Tente reformular." if lang == "pt" else "Couldn't identify a category for your question. Please rephrase."
        logger.warning("❌ Nenhuma categoria encontrada.")
        return {"response": msg}

    unique_answers = find_answers_faiss(user_input, indices_by_category, lang, categorias_detectadas)

    logger.info("Respostas candidatas:")
    for i, ans in enumerate(unique_answers[:5]):
        logger.info(f"{i+1}. {ans[:100]}...")

    if not unique_answers:
        msg = "Peço desculpa, não encontrei uma resposta adequada. Tente reformular a pergunta." if lang == "pt" else "Sorry, I couldn't find a suitable answer."
        logger.warning("❌ Nenhuma resposta encontrada.")
        return {"response": msg}

    state["last_possible_answers"] = unique_answers
    state["last_answer_index"] = 0

    logger.info(f"✅ Resposta enviada: {unique_answers[0][:150]}...\n")
    return {"response": unique_answers[0]}
