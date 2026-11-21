import json
import unittest
from unittest.mock import Mock, patch

import gradio as gr
import gradio_app
from strategy_lab import REFERENCE_SOURCE, acceptance_cases


class OfflineTests(unittest.TestCase):
    def test_provider_gate_is_server_side(self):
        for action in (
            gradio_app.generate,
            gradio_app.connect,
            gradio_app.preview,
            gradio_app.submit,
            gradio_app.refresh,
        ):
            provider = Mock(wraps=action)
            with self.subTest(action=action.__name__), self.assertRaises(gr.Error):
                gradio_app.connected_action(provider, False)()
            provider.assert_not_called()

    def test_altered_browser_inputs_cannot_enable_alpaca(self):
        evaluate = gradio_app.evaluation_action(False)
        with patch("gradio_app.paper_connection") as provider:
            for data, enabled in [
                ("Alpaca IEX", False),
                ("Synthetic", True),
                ("unknown", False),
            ]:
                with (
                    self.subTest(data=data, enabled=enabled),
                    self.assertRaises(gr.Error),
                ):
                    evaluate(REFERENCE_SOURCE, "[]", data, "AAPL", enabled)
            provider.assert_not_called()

    def test_synthetic_evaluation_needs_no_network(self):
        with (
            patch(
                "socket.socket.connect", side_effect=AssertionError("Network forbidden")
            ),
            patch("gradio_app.OpenAI", side_effect=AssertionError("No model client")),
            patch(
                "gradio_app.paper_connection", side_effect=AssertionError("No broker")
            ),
        ):
            scores, _, ledger, _ = gradio_app.evaluation_action(False)(
                REFERENCE_SOURCE,
                json.dumps(acceptance_cases()),
                "Synthetic",
                "AAPL",
                False,
            )
        self.assertEqual(len(ledger), 7)
        self.assertAlmostEqual(scores.iloc[0].final_equity, 9922.2408, places=4)

    def test_connected_gate_passes_arguments(self):
        action = Mock(return_value="ok")
        self.assertEqual(gradio_app.connected_action(action, True)(1, 2), "ok")
        action.assert_called_once_with(1, 2)

    def test_cli_does_not_read_dotenv_by_default(self):
        import app

        with (
            patch("sys.argv", ["app.py"]),
            patch("dotenv.load_dotenv") as dotenv,
            patch("gradio_app.build_ui") as build,
        ):
            app.main()
        dotenv.assert_not_called()
        build.assert_called_once_with(connected=False)
        self.assertFalse(
            build.return_value.queue.return_value.launch.call_args.kwargs["share"]
        )


if __name__ == "__main__":
    unittest.main()
