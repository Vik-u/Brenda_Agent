"""Streamlit interface for the BrendaChatbot."""

from __future__ import annotations

from typing import List

import streamlit as st

from src.services.chatbot import BrendaChatbot, ChatResult


@st.cache_resource(show_spinner=False)
def _load_chatbot(model_override: str | None) -> BrendaChatbot:
    return BrendaChatbot(model=model_override)


def _render_history(messages: List[dict], show_sql: bool) -> None:
    for entry in messages:
        role = entry["role"]
        content = entry["content"]
        if role == "user":
            st.markdown(f"**You:** {content}")
        else:
            st.markdown(f"**BrendaChatbot:** {content}")
            if show_sql and entry.get("sql"):
                with st.expander("Show SQL", expanded=False):
                    for statement in entry["sql"]:
                        st.code(statement, language="sql")


def main() -> None:
    st.set_page_config(page_title="BRENDA Chatbot", page_icon="🧪", layout="wide")
    st.title("BRENDA Chatbot")

    with st.sidebar:
        st.header("Settings")
        model_override = st.text_input(
            "Ollama model override",
            value="",
            help="Leave empty to use the configured default.",
        ) or None
        show_sql = st.checkbox("Show executed SQL", value=False)
        if st.button("Clear conversation"):
            st.session_state.messages = []
            st.experimental_rerun()

    try:
        bot = _load_chatbot(model_override)
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    if "messages" not in st.session_state:
        st.session_state.messages: List[dict] = []

    _render_history(st.session_state.messages, show_sql)

    with st.form("chat-form", clear_on_submit=True):
        question = st.text_area(
            "Ask a question about the BRENDA database",
            height=120,
            placeholder="e.g. Summarize inhibitors reported for EC 1.1.1.1",
        )
        submitted = st.form_submit_button("Send")

    if submitted and question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.spinner("Querying database..."):
            result: ChatResult = bot.ask(question)
        st.session_state.messages.append(
            {"role": "assistant", "content": result.answer, "sql": result.sql}
        )
        st.experimental_rerun()


if __name__ == "__main__":
    main()
