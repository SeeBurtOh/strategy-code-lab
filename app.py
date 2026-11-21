"""Local portfolio app. Offline unless --connected is explicitly supplied."""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connected",
        action="store_true",
        help="Load your .env and enable provider actions",
    )
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
    if args.connected:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    from gradio_app import build_ui

    ui = build_ui(connected=args.connected)
    print(
        "Connected mode: your own keys"
        if args.connected
        else "Offline demo: provider actions disabled"
    )
    ui.queue().launch(
        server_name="127.0.0.1",
        server_port=args.port,
        share=False,
        show_error=False,
        inbrowser=False,
    )


if __name__ == "__main__":
    main()
