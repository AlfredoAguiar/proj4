from langchain_ollama import OllamaEmbeddings

class Embeddings:
    def __init__(self, model_name: str):
        self.model_name = model_name


    def get_embedding_function(self):
        if self.model_name == "ollama":
            return OllamaEmbeddings(model="mxbai-embed-large:latest")

        else:
            raise ValueError(f"Unsupported embedding model: {self.model_name}")