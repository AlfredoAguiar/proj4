from .llm import LLM, OllamaModel
class LLMFactory:
    @staticmethod
    def create_llm(model_type: str, model_name: str) -> LLM:
        if model_type == 'ollama':
            return OllamaModel(model_name)
        else:
            raise ValueError(f"Unsupported model type: {model_type}")