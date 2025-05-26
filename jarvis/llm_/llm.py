from abc import ABC, abstractmethod
from langchain.prompts import ChatPromptTemplate
from langchain_ollama import OllamaLLM


PROMPT_TEMPLATE = """
Baseado **apenas** no seguinte contexto:

{context}

---

Responda à seguinte pergunta: {question}

### Regras:
1. Não inclua informações que não estejam no contexto fornecido.
2. Se a resposta não puder ser dada, diga: "Não foi possível encontrar uma resposta no contexto fornecido."
3. Use um estilo claro e direto.


Responda agora:
"""

class LLM(ABC):
    def __init__(self, model_name: str):
        self.model_name = model_name

    @abstractmethod
    def invoke(self, prompt: str) -> str:
        pass

    def generate_response(self, context: str, question: str) -> str:
        prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
        prompt = prompt_template.format(context=context, question=question)
        return self.invoke(prompt)



class OllamaModel(LLM):
    def __init__(self, model_name: str):
        super().__init__(model_name)
        self.model = OllamaLLM(model=model_name)

    def invoke(self, prompt: str) -> str:
        return self.model.invoke(prompt)


