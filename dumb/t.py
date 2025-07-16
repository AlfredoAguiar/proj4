import sys
import httpx
import unicodedata
from langdetect import detect, detect_langs
from difflib import SequenceMatcher
from sentence_transformers import SentenceTransformer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
import logging
import asyncio
from typing import Dict, List, Tuple, Optional

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

# Carrega embeddings caso deseje usar depois
model = SentenceTransformer("all-MiniLM-L6-v2")

# ────────────────────────────── CACHES EM MEMÓRIA ───────────────────────────── #

data_cache: Dict[str, dict] = {}
conversation_states: Dict[str, dict] = {}

# ────────────────────────────── FUNÇÕES UTILITÁRIAS ─────────────────────────── #

def normalize_text(text: str) -> str:
    """Lowercase e remove acentuação para comparações aproximadas."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', text.lower())
        if unicodedata.category(c) != 'Mn'
    )

def similarity(a: str, b: str) -> float:
    """Similaridade aproximada usando SequenceMatcher."""
    return SequenceMatcher(None, a, b).ratio()

def detect_categories(user_input: str, category_keywords: Dict[int, List[str]]) -> List[int]:
    norm_input = normalize_text(user_input)
    return [
        cid for cid, kws in category_keywords.items()
        if any(kw in norm_input for kw in kws)
    ]

def find_answers_ranked(user_input: str, questions: List[str], answers: List[str]) -> List[str]:
    user_norm = normalize_text(user_input)
    scored: List[Tuple[float, str]] = []
    for q, a in zip(questions, answers):
        sim = similarity(normalize_text(q), user_norm)
        if sim > 0.3:
            scored.append((sim, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored]

def is_feedback_negativo(user_input: str, lang: str, category_keywords: Dict[int, List[str]], feedback_negativo_ids: Dict[str, Optional[int]]) -> bool:
    fb_id = feedback_negativo_ids.get(lang)
    if fb_id is None:
        return False
    norm = normalize_text(user_input)
    return any(k in norm for k in category_keywords.get(fb_id, []))

def suggest_categories(user_input: str, category_keywords: Dict[int, List[str]], cat_names: Dict[int, str], k: int = 3) -> List[str]:
    norm_in = normalize_text(user_input)
    scored: List[Tuple[float, int]] = []
    for cid, kws in category_keywords.items():
        tokens = [cat_names.get(cid, "")] + kws
        best = max((similarity(norm_in, normalize_text(t)) for t in tokens), default=0.0)
        scored.append((best, cid))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [cat_names[cid] for score, cid in scored[:k] if score >= 0.10]

# ───────────────────────────── MODELOS Pydantic ─────────────────────────────── #

class MessageRequest(BaseModel):
    message: str
    session_id: str
    chatbot_id: str
    force_reload: bool = False

# ─────────────────────────── FUNÇÕES DE BACKEND API ─────────────────────────── #

async def fetch_categories(chatbot_id: str):
    url = f"http://localhost:3004/chatbot-categoria/{int(chatbot_id)}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Erro ao buscar categorias: {resp.text}")
        return resp.json()

async def fetch_faq_data(chatbot_id: int):
    cats = await fetch_categories(str(chatbot_id))
    faqs: List[dict] = []
    async with httpx.AsyncClient() as client:
        tasks = [client.get(f"http://localhost:3004/faq-categoria/?categoria_id={c['categoria_id']}") for c in cats]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Erro FAQ: {r}")
                continue
            if r.status_code != 200:
                logger.error(f"FAQ {r.status_code}: {r.text}")
                continue
            faqs.extend(r.json())
    return faqs


def detectar_idioma(texto: str) -> str:
    """
    Detecta o idioma e retorna 'pt' ou 'en'.
    Assume 'pt' como padrão caso a confiança seja baixa ou o texto seja curto.
    """
    texto = texto.strip()
    if len(texto) < 10:
        return "pt"
    try:
        idiomas = detect_langs(texto)
        for lang_prob in idiomas:
            if lang_prob.lang == "en" and lang_prob.prob > 0.90:
                return "en"
        return "pt"
    except Exception as e:
        logger.warning(f"Falha ao detectar idioma: {e}")
        return "pt"
# ───────────────────────────────── ENDPOINT PRINCIPAL ───────────────────────── #

@app.post("/chat_dumb")
async def chat(req: MessageRequest):
    logger.info("=== NOVA INTERAÇÃO ===")
    logger.info(f"Chatbot ID: {req.chatbot_id} | Session: {req.session_id}")
    logger.info(f"Pergunta: {req.message}")

    user_input = req.message.strip()
    if not user_input:
        return {"response": "Por favor, escreva algo."}

    chatbot_id = req.chatbot_id.strip()
    session_id = req.session_id.strip()

    # ─── Detecta idioma (fallback pt) ───
    lang = detectar_idioma(user_input)


    # ─── Reset cache se force_reload ───
    if req.force_reload and chatbot_id in data_cache:
        del data_cache[chatbot_id]

    # ─── Lazy‑load cache ───
    if chatbot_id not in data_cache:
        cats = await fetch_categories(chatbot_id)
        faqs = await fetch_faq_data(int(chatbot_id))

        category_keywords: Dict[int, List[str]] = {}
        feedback_ids: Dict[str, Optional[int]] = {"pt": None, "en": None}
        cat_names = {}

        for c in cats:
            cid = c["categoria_id"]
            kws = c.get("categoria", {}).get("keywords", [])
            category_keywords[cid] = [normalize_text(k) for k in kws]
            cat_names[cid] = c.get("categoria", {}).get("nome", f"Categoria {cid}")
            if cid == 999:
                feedback_ids["pt"] = cid
            elif cid == 998:
                feedback_ids["en"] = cid

        q_by_cat: Dict[Tuple[int, str], List[str]] = {}
        a_by_cat: Dict[Tuple[int, str], List[str]] = {}

        for f in faqs:
            cid = f["categoria_id"]
            faq = f.get("faq", {})
            q = faq.get("pergunta", "").strip()
            a = faq.get("resposta", "").strip()
            lang_raw = normalize_text(faq.get("idioma", "pt"))
            idioma = "pt" if lang_raw.startswith("pt") else "en"
            if not q or not a:
                continue
            key = (cid, idioma)
            q_by_cat.setdefault(key, []).append(q)
            a_by_cat.setdefault(key, []).append(a)

        data_cache[chatbot_id] = {
            "category_keywords": category_keywords,
            "questions_by_category": q_by_cat,
            "answers_by_category": a_by_cat,
            "feedback_negativo_ids": feedback_ids,
            "cat_names": cat_names,
        }

    # ─── Carrega variáveis do cache ───
    cache = data_cache[chatbot_id]
    category_keywords = cache["category_keywords"]
    q_by_cat = cache["questions_by_category"]
    a_by_cat = cache["answers_by_category"]
    feedback_ids = cache["feedback_negativo_ids"]
    cat_names = cache["cat_names"]

    # ─── Estado de sessão ───
    if session_id not in conversation_states:
        conversation_states[session_id] = {
            "language": lang,
            "last_possible_answers": [],
            "last_answer_index": 0,
            "last_question": "",
        }
    state = conversation_states[session_id]

    # ─── Feedback negativo? ───
    if is_feedback_negativo(user_input, lang, category_keywords, feedback_ids):
        idx = state.get("last_answer_index", 0) + 1
        poss = state.get("last_possible_answers", [])
        if idx < len(poss):
            state["last_answer_index"] = idx
            return {"response": poss[idx]}
        return {"response": "Lamento, não tenho mais respostas alternativas." if lang == "pt" else "Sorry, no more alternative answers."}

    # Reset estado para nova pergunta
    state.update({
        "last_possible_answers": [],
        "last_answer_index": 0,
        "last_question": user_input,
    })

    # ─── Detecta categorias ───
    detected = detect_categories(user_input, category_keywords)
    logger.info(f"Categorias detectadas: {detected}")

    if not detected:
        sugeridas = suggest_categories(user_input, category_keywords, cat_names)
        if sugeridas:
            msg = ("Não consegui identificar uma categoria exata. Talvez você queira saber sobre: " if lang == "pt" else "Couldn't detect an exact category. Maybe you meant: ") + ", ".join(sugeridas) + "."
            return {"response": msg, "categorias_sugeridas": sugeridas}
        return {"response": "Não consegui identificar uma categoria para sua pergunta. Tente reformular." if lang == "pt" else "Couldn't identify a category. Please rephrase."}

    # ─── Coleta respostas candidatas ───
    possible: List[str] = []
    for cid in detected:
        key = (cid, lang)
        qs = q_by_cat.get(key, [])
        ans = a_by_cat.get(key, [])
        possible.extend(find_answers_ranked(user_input, qs, ans))

    # Remove duplicadas preservando ordem
    seen: set = set()
    unique_answers = [a for a in possible if not (a in seen or seen.add(a))]

    if not unique_answers:
        msg = (
            "Peço desculpa, mas não consegui encontrar uma resposta adequada para a sua pergunta. "
            "Poderia tentar reformular a questão. "
            "Estou aqui para ajudar no que precisar!"
            if lang == "pt"
            else
            "I'm sorry, but I couldn't find a suitable answer for your question. "
            "Please try rephrasing it, be more specific. "
            "I'm here to help!"
        )
        logger.warning("❌ Nenhuma resposta encontrada.")
        return {
            "response": msg,

        }

    state["last_possible_answers"] = unique_answers
    state["last_answer_index"] = 0

    return {"response": unique_answers[0]}
