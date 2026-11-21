"""Execute the committed notebook with provider clients blocked; save nothing."""

import os
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager

ROOT = Path(__file__).resolve().parents[1]
os.environ["MPLBACKEND"] = "Agg"
nb = nbformat.read(ROOT / "alpaca_strategy_codegen.ipynb", as_version=4)
nb.cells.insert(
    0,
    nbformat.v4.new_code_cell(
        "from unittest.mock import patch\n"
        "_no_model = patch('openai.OpenAI', side_effect=AssertionError('Offline notebook called OpenAI'))\n"
        "_no_broker = patch('paper_broker.PaperBroker', side_effect=AssertionError('Offline notebook called Alpaca'))\n"
        "_no_model.start(); _no_broker.start()\n"
    ),
)
km = KernelManager(kernel_name="python3")
km.kernel_spec.argv[0] = sys.executable
client = NotebookClient(
    nb, timeout=120, km=km, resources={"metadata": {"path": str(ROOT)}}
)
try:
    client.execute()
finally:
    km.shutdown_kernel(now=True)
print("Notebook executed successfully with provider clients blocked; no output saved.")
