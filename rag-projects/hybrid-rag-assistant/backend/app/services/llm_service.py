import structlog
from google import genai
from google.genai import types

from app.config import settings
from app.prompts.chat_prompts import QUERY_REWRITE_PROMPT

log = structlog.get_logger()


class LLMService:
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model

    async def rewrite_query(
        self, history: list[dict], message: str
    ) -> str:
        if not history:
            return message
        history_text = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in history
        )
        prompt = QUERY_REWRITE_PROMPT.format(
            history=history_text, question=message
        )
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0),
        )
        rewritten = response.text.strip()
        log.info("query.rewritten", original=message, rewritten=rewritten)
        return rewritten

    async def generate(
        self,
        system_instruction: str,
        history: list[dict],
        user_message: str,
    ) -> str:
        contents: list[types.Content] = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0,
            ),
        )
        return response.text.strip()
