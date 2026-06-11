from openai import AsyncOpenAI
import logging
import asyncio
from typing import Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
    async def chat_completion(
        self,
        prompt: str,
        system_prompt: str = "You are an expert patent attorney assisting in invalidity analysis.",
        use_reasoning: bool = False,
        temperature: float = 0.1
    ) -> str:
        # Route model based on reasoning request
        model = settings.LLM_MODEL_REASONING if use_reasoning else settings.LLM_MODEL_ROUTINE
        
        # Attempt completion with backoff retries
        for attempt in range(4):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature,
                    max_tokens=settings.MAX_TOKENS_PER_CALL
                )
                
                return response.choices[0].message.content
                
            except Exception as e:
                logger.warning(f"LLM Call Attempt {attempt+1} failed: {e}")
                if attempt == 3:
                    raise e
                await asyncio.sleep(2 ** attempt)
                
        return ""

llm_client = LLMClient()
