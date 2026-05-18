"""Optional Hugging Face LLM client.
Install: pip install transformers accelerate torch
"""
from __future__ import annotations

class HuggingFaceLLMClient:
    def __init__(self, model_name: str, max_new_tokens: int = 160):
        from transformers import pipeline
        self.generator = pipeline("text-generation", model=model_name, device_map="auto")
        self.max_new_tokens = max_new_tokens

    def __call__(self, prompt: str) -> str:
        result = self.generator(prompt, max_new_tokens=self.max_new_tokens, do_sample=False, return_full_text=False)
        return result[0]["generated_text"]
