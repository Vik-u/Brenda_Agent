"""Gradio interface for the BrendaChatbot."""

from __future__ import annotations

import argparse
import socket
from typing import Dict, List, Tuple

import gradio as gr

from src.services.chatbot import BrendaChatbot, ChatResult


class ChatbotRegistry:
    """Cache BrendaChatbot instances keyed by model overrides."""

    def __init__(self) -> None:
        self._registry: Dict[str | None, BrendaChatbot] = {}

    def get(self, model_override: str | None) -> BrendaChatbot:
        if model_override not in self._registry:
            self._registry[model_override] = BrendaChatbot(model=model_override)
        return self._registry[model_override]


registry = ChatbotRegistry()


def _find_free_port(start: int = 8560, attempts: int = 200) -> int:
    for offset in range(attempts):
        port = start + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise OSError("Unable to find free port")


def _join_sql(sql: List[str]) -> str:
    if not sql:
        return ""
    newline = "\n"
    statements = (newline * 2).join(sql)
    return (newline * 2) + "```sql" + newline + statements + newline + "```"


def _chat(
    message: str,
    history: List[Tuple[str, str]],
    model_override: str,
    show_sql: bool,
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]], str]:
    override = (model_override or "").strip() or None
    try:
        bot = registry.get(override)
    except FileNotFoundError as exc:
        history.append((message, f"Error: {exc}"))
        return history, history, ""
    except Exception as exc:  # pragma: no cover
        history.append((message, f"Failed to initialise chatbot: {exc}"))
        return history, history, ""

    try:
        result: ChatResult = bot.ask(message)
    except Exception as exc:  # pragma: no cover
        history.append((message, f"Error while querying BRENDA: {exc}"))
        return history, history, ""

    answer = result.answer
    if show_sql:
        answer = f"{answer}{_join_sql(result.sql)}"
    history = history + [(message, answer)]
    return history, history, ""


def launch(*, port: int | None = None, share: bool = False) -> None:
    with gr.Blocks(title="BRENDA Gradio Chatbot", theme="soft") as demo:
        gr.Markdown("# 🧪 BRENDA Chatbot\nAsk about enzymes, kinetics, inhibitors, and literature.")

        with gr.Row():
            model_box = gr.Textbox(
                label="Ollama model override",
                placeholder="Leave blank to use default model",
            )
            show_sql = gr.Checkbox(label="Show executed SQL", value=False)

        history_state: gr.State = gr.State([])
        chatbot = gr.Chatbot(height=480)
        message_box = gr.Textbox(
            label="Question",
            placeholder="e.g. Summarize inhibitors reported for EC 1.1.1.1",
            lines=3,
        )
        send = gr.Button("Send", variant="primary")
        clear = gr.Button("Clear conversation", variant="secondary")

        send.click(
            _chat,
            inputs=[message_box, history_state, model_box, show_sql],
            outputs=[chatbot, history_state, message_box],
        )
        message_box.submit(
            _chat,
            inputs=[message_box, history_state, model_box, show_sql],
            outputs=[chatbot, history_state, message_box],
        )

        def _reset() -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]], str]:
            return [], [], ""

        clear.click(_reset, outputs=[chatbot, history_state, message_box])

    chosen_port = port or _find_free_port()
    print(f"Launching Gradio chatbot on http://127.0.0.1:{chosen_port}")
    demo.launch(
        server_name="127.0.0.1",
        server_port=chosen_port,
        share=share,
        show_api=False,
        inbrowser=False,
        quiet=True,
        max_threads=2,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the BRENDA Gradio chatbot")
    parser.add_argument("--port", type=int, help="Explicit port (default: auto)")
    parser.add_argument("--share", action="store_true", help="Enable public share link")
    args = parser.parse_args()
    launch(port=args.port, share=args.share)


if __name__ == "__main__":
    main()
