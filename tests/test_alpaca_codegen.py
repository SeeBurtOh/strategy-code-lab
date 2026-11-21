import sys
from pathlib import Path
import math
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace as NS
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from strategy_lab import (
    Strategy,
    StrategyError,
    REFERENCE_SOURCE,
    DEFAULT_SPEC,
    acceptance_cases,
    generate_strategy,
    backtest,
    synthetic_bars,
    check_cases,
)
from paper_broker import PaperBroker, NY, APIError


class StrategyTests(unittest.TestCase):
    def test_reference_and_random_oracle(self):
        s = Strategy(REFERENCE_SOURCE)
        check_cases(s, acceptance_cases())
        rng = np.random.default_rng(921)
        for length in range(500):
            closes = np.exp(rng.normal(4, 0.3, length)).tolist()
            expected = (
                int(np.mean(closes[-10:]) > np.mean(closes[-30:]))
                if length >= 30
                else 0
            )
            self.assertEqual(s(closes), expected)

    def test_bad_syntax_and_effects(self):
        for code in [
            "import os\ndef signal(closes):\n return 1",
            "def signal(closes):\n return closes.__class__",
            "def signal(closes):\n while 1:\n  pass",
            "def signal(closes):\n return __import__(1)",
            "def signal(closes):\n return 10 ** 100",
            "def signal(closes=[]):\n return 1",
            "def signal(closes):\n closes[0]=1\n return 1",
            "def signal(closes):\n sum=1\n return 1",
            "def signal(closes):\n def f():\n  return 1\n return 1",
            'def signal(closes):\n return "1"',
        ]:
            with self.subTest(code=code), self.assertRaises(StrategyError):
                Strategy(code)

    def test_runtime_contract(self):
        for source in [
            "def signal(closes):\n return 2",
            "def signal(closes):\n return 1.0",
            "def signal(closes):\n return 1 > 0",
            "def signal(closes):\n return 1 / 0",
            "def signal(closes):\n a=1",
            "def signal(closes):\n x=closes * 1000000\n return 1",
            "def signal(closes):\n return closes[100]",
        ]:
            with self.subTest(source=source), self.assertRaises(StrategyError):
                Strategy(source)([100])

    def test_bad_history(self):
        for values in [[float("nan")], [float("inf")], [0], [-1], [100] * 10001]:
            with self.assertRaises(StrategyError):
                Strategy(REFERENCE_SOURCE)(values)

    def test_boolean_slicing_arithmetic(self):
        s = Strategy(
            "def signal(closes):\n if len(closes) >= 2 and not (closes[-1] < closes[-2]):\n  v = max(closes[-2:]) - min(closes[-2:])\n  if abs(v) >= 1:\n   return 1\n return 0"
        )
        self.assertEqual(s([]), 0)
        self.assertEqual(s([3, 5]), 1)
        self.assertEqual(s([5, 3]), 0)

    def test_generation_repair_and_records(self):
        client = Mock()

        def response(text):
            return NS(
                output_text=text,
                status="completed",
                usage=NS(input_tokens=20, output_tokens=30),
            )

        client.responses.create.side_effect = [
            response("def signal(closes):\n return 1"),
            response(REFERENCE_SOURCE),
        ]
        candidate, log = generate_strategy(
            client, "test-model", DEFAULT_SPEC, acceptance_cases()
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(log.passed.tolist(), [False, True])
        self.assertEqual(log.input_tokens.tolist(), [20, 20])
        self.assertIn(
            "Validation error", client.responses.create.call_args.kwargs["input"]
        )
        self.assertFalse(client.responses.create.call_args.kwargs["store"])

    def test_generation_exhaustion(self):
        client = Mock()
        client.responses.create.return_value = NS(
            output_text="", status="incomplete", usage=None
        )
        candidate, log = generate_strategy(
            client, "model", DEFAULT_SPEC, acceptance_cases()
        )
        self.assertIsNone(candidate)
        self.assertEqual(len(log), 2)
        self.assertFalse(log.passed.any())


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.bars = pd.DataFrame(
            {"open": [10.0, 20.0, 30.0], "close": [10.0, 25.0, 30.0]},
            index=pd.date_range("2024-01-01", periods=3),
        )

    def test_next_open_and_roundtrip(self):
        seen = []

        def signal(c):
            seen.append(c.copy())
            return int(len(c) == 1)

        curve, ledger, m = backtest(
            self.bars,
            signal,
            initial_cash=100,
            allocation=1,
            fee_bps=0,
            slippage_bps=0,
            start=1,
        )
        self.assertEqual(seen, [[10.0], [10.0, 25.0]])
        self.assertEqual(ledger.fill.tolist(), [20.0, 30.0])
        self.assertEqual(ledger.qty.tolist(), [5, 5])
        self.assertEqual(m["final_equity"], 150.0)
        self.assertTrue((curve.cash >= 0).all())

    def test_initial_loss_drawdown(self):
        bars = self.bars.copy()
        bars.loc[:, "close"] = [10.0, 10.0, 10.0]
        _, _, m = backtest(
            bars,
            lambda c: 1,
            initial_cash=100,
            allocation=1,
            fee_bps=0,
            slippage_bps=0,
            start=1,
        )
        self.assertEqual(m["max_drawdown_pct"], -50.0)
        self.assertEqual(m["return_pct"], -50.0)

    def test_costs_and_no_forced_close(self):
        _, ledger, m = backtest(
            self.bars,
            lambda c: 1,
            initial_cash=100,
            allocation=1,
            fee_bps=10,
            slippage_bps=10,
            start=1,
        )
        self.assertEqual(ledger.side.tolist(), ["buy"])
        self.assertGreater(m["fees"], 0)
        self.assertLess(m["final_equity"], 150.0)

    def test_invalid_data_and_config(self):
        for bars in [
            self.bars.iloc[::-1],
            self.bars.set_axis([0, 1, 2]),
            self.bars.replace(20.0, float("nan")),
        ]:
            with self.assertRaises(ValueError):
                backtest(bars, lambda c: 1, start=1)
        for kwargs in [
            {"allocation": 1.1},
            {"initial_cash": -10},
            {"slippage_bps": float("nan")},
            {"start": 3},
        ]:
            with self.assertRaises(ValueError):
                backtest(self.bars, lambda c: 1, **kwargs)

    def test_no_capital_or_negative_holdings(self):
        for seed in range(10):
            curve, _, _ = backtest(synthetic_bars(seed), Strategy(REFERENCE_SOURCE))
            self.assertTrue((curve.cash >= 0).all())
            self.assertTrue((curve.shares >= 0).all())


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.broker = PaperBroker.__new__(PaperBroker)
        self.broker.trading = Mock()
        self.broker.data = Mock()
        self.t = self.broker.trading
        self.d = self.broker.data
        self.now = datetime.now(NY)
        self.last = self.now.date() - timedelta(days=1)
        self.t.get_clock.return_value = NS(is_open=True)
        self.t.get_account.return_value = NS(
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
            equity="10000",
            cash="10000",
        )
        self.t.get_asset.return_value = NS(tradable=True, asset_class="us_equity")
        self.t.get_orders.return_value = []
        self.t.get_calendar.return_value = [NS(date=self.last)]
        self.t.get_all_positions.return_value = []
        self.t.get_order_by_client_id.side_effect = APIError(
            "{}", NS(response=NS(status_code=404))
        )
        self.d.get_stock_latest_quote.return_value = {
            "AAPL": NS(timestamp=self.now, bid_price=99.9, ask_price=100.0)
        }
        self.frame = pd.DataFrame(
            {"open": np.arange(50.0, 90.0), "close": np.arange(50.0, 90.0)},
            index=pd.date_range(end=self.last, periods=40, tz=NY),
        )
        self.broker.bars = Mock(return_value=self.frame)
        self.strategy = Strategy(REFERENCE_SOURCE)

    def test_constructor_is_paper_only(self):
        with (
            patch.dict(
                "os.environ",
                {"ALPACA_PAPER_API_KEY": "fake", "ALPACA_PAPER_SECRET_KEY": "fake"},
            ),
            patch("paper_broker.TradingClient") as t,
            patch("paper_broker.StockHistoricalDataClient"),
        ):
            PaperBroker()
            t.assert_called_once_with("fake", "fake", paper=True)

    def test_buy_preview_no_mutation(self):
        plan = self.broker.preview(self.strategy)
        self.assertEqual(plan["action"], "buy")
        self.assertEqual(plan["qty"], 9)
        self.assertLessEqual(plan["estimated_notional"], 1000)
        self.t.submit_order.assert_not_called()
        self.assertEqual(
            plan["client_order_id"],
            self.broker.preview(self.strategy)["client_order_id"],
        )

    def test_custom_entry_budget_survives_submit(self):
        plan = self.broker.preview(self.strategy, max_notional=250)
        self.t.submit_order.return_value = NS(
            client_order_id=plan["client_order_id"],
            status="accepted",
            filled_qty="0",
            filled_avg_price=None,
        )
        self.broker.submit(self.strategy, plan, max_notional=250)
        self.assertEqual(self.t.submit_order.call_args.kwargs["order_data"].qty, 2)

    def test_noninteger_signal_rejected_before_hold(self):
        with self.assertRaises(ValueError):
            self.broker.preview(lambda c: False)

    def test_market_closed(self):
        self.t.get_clock.return_value.is_open = False
        self.assertEqual(self.broker.preview(self.strategy)["action"], "hold")
        self.t.get_account.assert_not_called()

    def test_open_orders_block(self):
        self.t.get_orders.return_value = [NS(id="existing")]
        self.assertEqual(self.broker.preview(self.strategy)["action"], "hold")

    def test_bad_data_blocks(self):
        self.broker.bars.return_value = self.frame.iloc[:-1]
        with self.assertRaises(ValueError):
            self.broker.preview(self.strategy)

    def test_stale_quotes_block(self):
        self.d.get_stock_latest_quote.return_value["AAPL"].timestamp = (
            self.now - timedelta(minutes=10)
        )
        with self.assertRaises(ValueError):
            self.broker.preview(self.strategy)

    def test_cash_no_margin(self):
        self.t.get_account.return_value.cash = "50"
        self.assertEqual(self.broker.preview(self.strategy)["action"], "hold")

    def test_fractional_and_short_positions_rejected(self):
        for qty in ["0.5", "-1"]:
            self.t.get_all_positions.return_value = [NS(symbol="AAPL", qty=qty)]
            with self.assertRaises(ValueError):
                self.broker.preview(self.strategy)

    def test_existing_position_holds(self):
        self.t.get_all_positions.return_value = [NS(symbol="AAPL", qty="2")]
        self.assertEqual(self.broker.preview(self.strategy)["action"], "hold")

    def test_sell_exit(self):
        self.t.get_all_positions.return_value = [NS(symbol="AAPL", qty="2")]
        plan = self.broker.preview(Strategy("def signal(closes):\n return 0"))
        self.assertEqual(plan["action"], "sell")
        self.assertEqual(plan["qty"], 2)

    def test_duplicate_client_id_blocks(self):
        self.t.get_order_by_client_id.side_effect = None
        self.t.get_order_by_client_id.return_value = NS(status="filled")
        self.assertEqual(self.broker.preview(self.strategy)["action"], "hold")

    def test_lookup_auth_failure_not_swallowed(self):
        self.t.get_order_by_client_id.side_effect = APIError(
            "{}", NS(response=NS(status_code=401))
        )
        with self.assertRaises(APIError):
            self.broker.preview(self.strategy)

    def test_submit_builds_valid_sdk_limit_request(self):
        plan = self.broker.preview(self.strategy)
        self.t.submit_order.return_value = NS(
            client_order_id=plan["client_order_id"],
            status="accepted",
            filled_qty="0",
            filled_avg_price=None,
        )
        result = self.broker.submit(self.strategy, plan)
        request = self.t.submit_order.call_args.kwargs["order_data"]
        self.assertEqual(request.qty, 9)
        self.assertEqual(request.limit_price, 100.1)
        self.assertEqual(str(request.type), "OrderType.LIMIT")
        self.assertEqual(result["filled_qty"], "0")

    def test_changed_quote_blocks_submission(self):
        plan = self.broker.preview(self.strategy)
        self.d.get_stock_latest_quote.return_value["AAPL"].ask_price = 101.0
        with self.assertRaises(ValueError):
            self.broker.submit(self.strategy, plan)
        self.t.submit_order.assert_not_called()

    def test_timeout_reconciles_existing_order(self):
        plan = self.broker.preview(self.strategy)
        order = NS(
            client_order_id=plan["client_order_id"],
            status="accepted",
            filled_qty="0",
            filled_avg_price=None,
        )
        self.t.get_order_by_client_id.side_effect = [
            APIError("{}", NS(response=NS(status_code=404))),
            order,
        ]
        self.t.submit_order.side_effect = TimeoutError("Unknown submission result")
        result = self.broker.submit(self.strategy, plan)
        self.assertEqual(result["client_order_id"], plan["client_order_id"])
        self.t.submit_order.assert_called_once()

    def test_ambiguous_failure_without_order_raises(self):
        plan = self.broker.preview(self.strategy)
        self.t.submit_order.side_effect = TimeoutError("Unknown submission result")
        with self.assertRaises(TimeoutError):
            self.broker.submit(self.strategy, plan)
        self.t.submit_order.assert_called_once()

    def test_historical_adapter_excludes_end(self):
        # Restore real method, mocking only the network boundary.
        broker = self.broker
        del broker.bars
        index = pd.MultiIndex.from_product(
            [["AAPL"], pd.date_range("2024-01-02", periods=4, tz=NY)],
            names=["symbol", "timestamp"],
        )
        df = pd.DataFrame(
            {"open": [1.0, 2.0, 3.0, 4.0], "close": [1.0, 2.0, 3.0, 4.0]}, index=index
        )
        self.d.get_stock_bars.return_value = NS(data={"AAPL": [1]}, df=df)
        result = broker.bars("AAPL", "2024-01-02", "2024-01-05")
        self.assertEqual(len(result), 3)
        request = self.d.get_stock_bars.call_args.args[0]
        self.assertEqual(str(request.feed), "DataFeed.IEX")


if __name__ == "__main__":
    unittest.main(verbosity=2)
