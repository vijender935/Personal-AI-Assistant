"""
Simple ChatGPT-style local UI for the Personal AI Agent.
"""

import gradio as gr

from agent import init_db, run_agent, MODEL

init_db()


def chat(message, history, session_id):
    if not message or not message.strip():
        return history

    answer = run_agent(message.strip(), session_id=session_id, verbose=False)
    history = history or []
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": answer})
    return history


def new_session():
    import time
    return f"session-{int(time.time())}"


with gr.Blocks(title="Personal AI Agent") as demo:
    gr.Markdown("# 🤖 Personal AI Agent")
    gr.Markdown(f"**Model:** `{MODEL}`")

    session = gr.State("default")
    chatbot = gr.Chatbot(type="messages", height=600)

    with gr.Row():
        msg = gr.Textbox(
            placeholder="Ask anything...",
            scale=8,
            show_label=False,
        )
        send = gr.Button("➤", scale=1)

    with gr.Row():
        new_chat = gr.Button("🆕 New Chat")
        remember = gr.Textbox(
            placeholder="Optional: /remember ...",
            show_label=False,
            scale=3,
        )

    def submit(message, history, sid):
        updated = chat(message, history, sid)
        return "", updated

    send.click(submit, [msg, chatbot, session], [msg, chatbot])
    msg.submit(submit, [msg, chatbot, session], [msg, chatbot])

    new_chat.click(
        lambda: ([], new_session()),
        outputs=[chatbot, session],
    )

if __name__ == "__main__":
    demo.launch()
