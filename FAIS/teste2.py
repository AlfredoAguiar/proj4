import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

def load_questions_answers(path):
    questions = []
    answers = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            q, a = line.strip().split("\t")
            questions.append(q)
            answers.append(a)
    return questions, answers

def search_answers(index, model, questions, answers, user_question, threshold=1.0, top_k=3):
    user_embedding = model.encode([user_question]).astype('float32')
    distances, indices = index.search(user_embedding, top_k)
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if dist <= threshold:
            results.append((dist, answers[idx]))
    return results

if __name__ == "__main__":
    model = SentenceTransformer('all-MiniLM-L6-v2')
    index = faiss.read_index("faiss.index")
    questions, answers = load_questions_answers("../jarvis/perguntas_respostas.txt")

    print("Chatbot started! Type 'exit' to quit.")
    while True:
        user_input = input("You: ").strip().lower()
        if user_input == "exit":
            print("Bot: Goodbye!")
            break
        results = search_answers(index, model, questions, answers, user_input)
        if results:
            print("Bot: Here are some answers:")
            for dist, resp in results:
                print(f"  (distance {dist:.2f}) - {resp}")
        else:
            print("Bot: Sorry, I couldn't find a suitable answer.")
