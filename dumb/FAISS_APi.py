import os
import unicodedata
from langdetect import detect
import faiss
from sentence_transformers import SentenceTransformer
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app2 = FastAPI()
app2.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BOTS_FOLDER = "bots"
SELECTED_BOT = "dumb_faq"
BOT_PATH = os.path.join(BOTS_FOLDER, SELECTED_BOT)
MODEL = SentenceTransformer("all-MiniLM-L6-v2")
DATA_CACHE = {}


# -------- Utilidades --------
def normalize_text(text):
    text = text.lower()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')


def load_qa(path):
    questions, answers = [], []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 2:
                questions.append(parts[0])
                answers.append(parts[1])
    return questions, answers


def search_faiss(msg, index, answers, top_k=3, max_distance=10):
    msg_norm = normalize_text(msg)
    emb = MODEL.encode([msg_norm]).astype('float32')
    distances, indices = index.search(emb, top_k)

    print("Distances returned by FAISS:", distances[0])  # Debugging

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < len(answers) and dist <= max_distance:
            results.append(answers[idx])
    return results


def load_negative_feedback(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return set(normalize_text(line.strip()) for line in f if line.strip())


def is_negative_feedback(user_input, neg_phrases):
    user_norm = normalize_text(user_input)
    for phrase in neg_phrases:
        if phrase in user_norm:
            if f" {phrase} " in f" {user_norm} " or user_norm.startswith(phrase) or user_norm.endswith(phrase):
                return True
    return False


def load_data(language):
    suffix = f"_{language}"
    all_questions, all_answers = [], []
    all_embeddings = []
    index = None

    # Carregar todos os arquivos *_qa_<lang>.txt
    for file in os.listdir(BOT_PATH):
        if file.endswith(f"_qa{suffix}.txt"):
            base_name = file.replace(".txt", "")
            qa_path = os.path.join(BOT_PATH, file)
            index_path = os.path.join(BOT_PATH, f"{base_name}.index")
            answers_path = os.path.join(BOT_PATH, f"{base_name}.answers")

            # Carrega QAs
            questions, answers = load_qa(qa_path)
            all_questions.extend(questions)

            # Carrega respostas
            if os.path.exists(answers_path):
                with open(answers_path, "r", encoding="utf-8") as f:
                    all_answers.extend([line.strip() for line in f if line.strip()])
            else:
                all_answers.extend(answers)

            # Carrega índice FAISS
            if os.path.exists(index_path):
                sub_index = faiss.read_index(index_path)
                if not index:
                    index = sub_index
                else:
                    index.merge_from(sub_index)

    # Carregar frases negativas
    neg_path = os.path.join(BOT_PATH, f"negative_feedback_{language}.txt")
    neg_feedback = load_negative_feedback(neg_path)

    return all_questions, all_answers, index, neg_feedback


# -------- Estado Temporário --------
CONVERSATION_STATE = {
    "last_question": None,
    "last_answers": [],
    "last_index": 0,
    "negative_count": 0
}


# -------- API --------
class MessageRequest(BaseModel):
    message: str


@app2.post("/chat_2")
async def chat(req: MessageRequest):
    msg = req.message.strip()
    try:
        lang = detect(msg)
        lang = "pt" if lang == "pt" else "en"
    except:
        lang = "pt"

    if lang not in DATA_CACHE:
        DATA_CACHE[lang] = load_data(lang)

    questions, answers, index, neg_feedback = DATA_CACHE[lang]

    if not index or not answers:
        return {"response": "Dados não disponíveis." if lang == "pt" else "Data not available."}

    # Verifica feedback negativo
    if is_negative_feedback(msg, neg_feedback):
        CONVERSATION_STATE["negative_count"] += 1
        if CONVERSATION_STATE["last_answers"] and CONVERSATION_STATE["last_index"] + 1 < len(CONVERSATION_STATE["last_answers"]):
            CONVERSATION_STATE["last_index"] += 1
            return {"response": CONVERSATION_STATE["last_answers"][CONVERSATION_STATE["last_index"]]}
        return {"response": "Não tenho mais respostas possíveis." if lang == "pt" else "No more possible answers."}

    # Reset
    CONVERSATION_STATE["negative_count"] = 0
    CONVERSATION_STATE["last_question"] = msg
    CONVERSATION_STATE["last_index"] = 0

    faiss_results = search_faiss(msg, index, answers)
    if faiss_results:
        CONVERSATION_STATE["last_answers"] = faiss_results
        return {"response": faiss_results[0]}

    return {"response": "Não encontrei resposta adequada." if lang == "pt" else "Couldn't find a suitable answer."}
