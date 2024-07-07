import logging

import anthropic

from .completion_service import CompletionService


class ClaudeCompletionService(CompletionService):
    client = None
    context = None

    def __init__(self, api_key, predefined_context):
        if api_key is not None:
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            raise Exception("Claude API key is required")

        if predefined_context is not None:
            self.context = predefined_context

    def get_completion(self, model="claude-3-sonnet-20240229", temperature=0.8, messages=None):
        if self.client is not None:
            prompt = {"role": "user", "content": messages}

            response = self.client.messages.create(
                messages=[prompt],
                model=model,
                max_tokens=4096,
                temperature=temperature
            )
            logging.info(response)
            # Возвращаем текст первого блока контента
            return response.content[0].text
        else:
            raise Exception("Anthropic client is not initialized")