import sys
from pathlib import Path
import json
import unittest
from unittest.mock import patch, Mock
import pandas as pd
import gradio as gr
import gradio_app as app
from strategy_lab import Strategy, REFERENCE_SOURCE, acceptance_cases


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.cases = json.dumps(acceptance_cases())
        self.plan = {
            "action": "buy",
            "symbol": "AAPL",
            "qty": 1,
            "limit_price": 100.1,
            "client_order_id": "test-id",
        }
        self.broker = Mock()
        self.broker.preview.return_value = self.plan
        self.broker.submit.return_value = {
            "client_order_id": "test-id",
            "status": "accepted",
            "filled_qty": "0",
        }

    def test_build_has_luna_default_and_no_network(self):
        with (
            patch("gradio_app.OpenAI") as model,
            patch("gradio_app.paper_connection") as broker,
        ):
            ui = app.build_ui()
            self.assertTrue(
                any(
                    c.get("props", {}).get("value") == "gpt-6-luna"
                    for c in ui.config["components"]
                )
            )
            model.assert_not_called()
            broker.assert_not_called()
            ui.close()

    def test_synthetic_backtest(self):
        scores, chart, ledger, message = app.evaluate(
            REFERENCE_SOURCE, self.cases, "Synthetic", "AAPL", False
        )
        self.assertAlmostEqual(scores.iloc[0].return_pct, -0.7776, places=4)
        self.assertEqual(len(ledger), 7)
        self.assertEqual(set(chart.strategy), {"Current strategy", "Buy and hold"})
        self.assertIn("Synthetic", message)

    def test_changed_rule_fails_examples(self):
        with self.assertRaises(gr.Error):
            app.evaluate(
                "def signal(closes):\n return 1", self.cases, "Synthetic", "AAPL", False
            )

    def test_invalid_case_shape(self):
        for data in ["{}", "[]", "[[[100], true]]", '[["bad", 1]]']:
            with self.subTest(data=data), self.assertRaises(ValueError):
                app.read_cases(data)

    def test_paper_disabled(self):
        with self.assertRaises(gr.Error):
            app.connect(False)

    def test_preview_returns_bound_snapshot_without_submission(self):
        with patch("gradio_app.paper_connection", return_value=self.broker):
            plan, snapshot, reviewed = app.preview(
                REFERENCE_SOURCE, self.cases, "aapl", 500, True
            )
        self.assertEqual(snapshot["symbol"], "AAPL")
        self.assertFalse(reviewed)
        self.assertEqual(plan, self.plan)
        self.broker.submit.assert_not_called()

    def test_review_required(self):
        with self.assertRaises(gr.Error):
            app.submit(REFERENCE_SOURCE, self.cases, "AAPL", 500, True, False, None)

    def test_changed_input_blocks_submission(self):
        with patch("gradio_app.paper_connection", return_value=self.broker):
            _, snapshot, _ = app.preview(
                REFERENCE_SOURCE, self.cases, "AAPL", 500, True
            )
            for source, symbol, budget, cases in [
                (REFERENCE_SOURCE, "MSFT", 500, self.cases),
                (REFERENCE_SOURCE, "AAPL", 550, self.cases),
                (REFERENCE_SOURCE + "\n", "AAPL", 500, self.cases),
                (REFERENCE_SOURCE, "AAPL", 500, "[]"),
            ]:
                with self.assertRaises(gr.Error):
                    app.submit(source, cases, symbol, budget, True, True, snapshot)
        self.broker.submit.assert_not_called()

    def test_submit_clears_preview_and_review(self):
        with patch("gradio_app.paper_connection", return_value=self.broker):
            _, snapshot, _ = app.preview(
                REFERENCE_SOURCE, self.cases, "AAPL", 500, True
            )
            result, order_id, snapshot, reviewed, plan = app.submit(
                REFERENCE_SOURCE, self.cases, "AAPL", 500, True, True, snapshot
            )
        self.assertEqual(order_id, "test-id")
        self.assertIsNone(snapshot)
        self.assertIsNone(plan)
        self.assertFalse(reviewed)
        self.assertEqual(self.broker.submit.call_args.kwargs["max_notional"], 500)

    def test_refresh_needs_order(self):
        with self.assertRaises(gr.Error):
            app.refresh(True, "")

    def test_refresh_reads_existing_order(self):
        with patch("gradio_app.paper_connection", return_value=self.broker):
            app.refresh(True, "test-id")
        self.broker.order_status.assert_called_once_with("test-id")

    def test_generation_uses_selected_model(self):
        log = pd.DataFrame([{"source": REFERENCE_SOURCE, "passed": True}])
        with (
            patch("gradio_app.OpenAI"),
            patch(
                "gradio_app.generate_strategy",
                return_value=(Strategy(REFERENCE_SOURCE), log),
            ) as generate,
        ):
            source, shown, status = app.generate("rule", "gpt-6-luna", self.cases)
        self.assertEqual(source, REFERENCE_SOURCE)
        self.assertNotIn("source", shown.columns)
        self.assertEqual(generate.call_args.args[1], "gpt-6-luna")

    def test_generation_failure_clears_source(self):
        with (
            patch("gradio_app.OpenAI"),
            patch(
                "gradio_app.generate_strategy",
                return_value=(None, pd.DataFrame([{"source": "bad", "passed": False}])),
            ),
        ):
            source, _, status = app.generate("rule", "gpt-6-luna", self.cases)
        self.assertEqual(source, "")
        self.assertIn("failed", status)

    def test_provider_exception_text_not_exposed(self):
        with patch(
            "gradio_app.paper_connection",
            side_effect=RuntimeError("sk-sensitive-example"),
        ):
            with self.assertRaises(gr.Error) as context:
                app.connect(True)
        self.assertNotIn("sk-sensitive", str(context.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
