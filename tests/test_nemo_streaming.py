import queue
import unittest
from unittest.mock import mock_open, patch

from src.services.audio_service import AudioTranscriptionService
from src.services.nemo_streaming import extract_hotword_phrases


class HotwordParsingTests(unittest.TestCase):
    def test_extracts_terms_from_generated_course_context(self):
        response = """This lecture discusses neural networks.

Key technical terms include:
Transformer architecture, attention blocks,
eigenvalue, attention blocks.

All technical terms should be transcribed accurately using their standard spelling.
"""
        self.assertEqual(
            extract_hotword_phrases(response),
            ["Transformer architecture", "attention blocks", "eigenvalue"],
        )

    def test_limits_phrases_and_accepts_plain_lists(self):
        self.assertEqual(
            extract_hotword_phrases("one; two\nthree", max_phrases=2),
            ["one", "two"],
        )


class EventMappingTests(unittest.TestCase):
    def setUp(self):
        self.service = AudioTranscriptionService()

    def test_deltas_build_one_partial_caption(self):
        partial = self.service._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "delta": "attention",
            },
            "",
        )
        partial = self.service._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "delta": " blocks",
            },
            partial,
        )
        self.assertEqual(partial, "attention blocks")
        self.assertEqual(
            self.service.partial_output_q.get_nowait().text,
            "attention",
        )
        self.assertEqual(
            self.service.partial_output_q.get_nowait().text,
            "attention blocks",
        )

    def test_completed_event_creates_accurate_and_clears_partial(self):
        with patch("builtins.open", mock_open()):
            partial = self.service._handle_event(
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "transcript": "Attention blocks improve the representation.",
                },
                "unfinished",
            )
        self.assertEqual(partial, "")
        self.assertEqual(
            self.service.accurate_output_q.get_nowait().text,
            "Attention blocks improve the representation.",
        )
        self.assertEqual(self.service.partial_output_q.get_nowait().text, "")
        with self.assertRaises(queue.Empty):
            self.service.accurate_output_q.get_nowait()


if __name__ == "__main__":
    unittest.main()
