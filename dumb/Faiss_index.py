import os
import faiss
from sentence_transformers import SentenceTransformer

def load_faq_file(path):
    questions = []
    answers = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        question = ""
        answer = ""
        for line in lines:
            line = line.strip()
            if line.startswith("P:"):
                question = line[2:].strip()
            elif line.startswith("R:"):
                answer = line[2:].strip()
                if question and answer:
                    questions.append(question)
                    answers.append(answer)
                    question, answer = "", ""
    return questions, answers

def build_and_save_indexes(faq_folder, model, index_folder):
    if not os.path.exists(index_folder):
        os.makedirs(index_folder)

    for filename in os.listdir(faq_folder):
        if filename.endswith(".txt"):
            category = filename.replace("faq_", "").replace(".txt", "").lower()
            path = os.path.join(faq_folder, filename)
            questions, answers = load_faq_file(path)
            if questions:
                q_embeds = model.encode(questions).astype('float32')
                index = faiss.IndexFlatL2(q_embeds.shape[1])
                index.add(q_embeds)

                # Salva o índice no disco
                faiss.write_index(index, os.path.join(index_folder, f"{category}.index"))

                # Salva também perguntas e respostas para carregar depois
                with open(os.path.join(index_folder, f"{category}_qa.txt"), "w", encoding="utf-8") as f:
                    for q, a in zip(questions, answers):
                        f.write(f"{q}\t{a}\n")

if __name__ == "__main__":
    model = SentenceTransformer('all-MiniLM-L6-v2')
    faq_folder = "bots/dumb_faq"
    index_folder = "faiss_indexes"

    build_and_save_indexes(faq_folder, model, index_folder)
    print("Índices criados e salvos!")
