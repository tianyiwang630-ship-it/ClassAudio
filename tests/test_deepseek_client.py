import types
import unittest
from unittest.mock import patch

from src.agent import llm


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = types.SimpleNamespace(content="generated text")
        choice = types.SimpleNamespace(message=message)
        return types.SimpleNamespace(choices=[choice])


class FakeOpenAI:
    instances = []

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.chat = types.SimpleNamespace(completions=FakeCompletions())
        self.__class__.instances.append(self)


class DeepSeekClientTests(unittest.TestCase):
    def setUp(self):
        FakeOpenAI.instances.clear()

    def test_client_uses_supplied_api_configuration(self):
        with patch.object(llm, "OpenAI", FakeOpenAI):
            client = llm.DeepSeekClient(
                api_key="test-key",
                base_url="https://example.invalid",
                model_name="test-model",
            )

        self.assertEqual(
            FakeOpenAI.instances[0].init_kwargs,
            {"api_key": "test-key", "base_url": "https://example.invalid"},
        )
        self.assertEqual(client.model_name, "test-model")

    def test_client_rejects_missing_api_key(self):
        with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
            llm.DeepSeekClient(api_key="", base_url="https://api.deepseek.com")

    def test_generate_uses_configured_model_and_returns_message(self):
        with patch.object(llm, "OpenAI", FakeOpenAI):
            client = llm.DeepSeekClient(
                api_key="test-key",
                base_url="https://api.deepseek.com",
                model_name="deepseek-v4-flash",
            )
            result = client.generate("hello")

        call = FakeOpenAI.instances[0].chat.completions.calls[0]
        self.assertEqual(call["model"], "deepseek-v4-flash")
        self.assertEqual(call["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(result, "generated text")


if __name__ == "__main__":
    unittest.main()
