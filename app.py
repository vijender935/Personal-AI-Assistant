"""Simple local ChatGPT-style UI."""
from __future__ import annotations
import time
import gradio as gr
from agent import MODEL, init_db, run_agent
init_db()

def new_session() -> str: return f"session-{time.time_ns()}"

def submit(message: str, history: list[dict] | None, session_id: str):
    if not message or not message.strip(): return "", history or []
    history = history or []
    answer = run_agent(message.strip(), session_id=session_id, verbose=False)
    return "", history + [{"role":"user","content":message.strip()},{"role":"assistant","content":answer}]

with gr.Blocks(title="Personal AI Agent") as demo:
    gr.Markdown("# 🤖 Personal AI Agent")
    gr.Markdown(f"**Model:** `{MODEL}`")
    session=gr.State("default")
    chatbot=gr.Chatbot(type="messages",height=600)
    with gr.Row():
        msg=gr.Textbox(placeholder="Ask anything...",scale=8,show_label=False)
        send=gr.Button("➤",scale=1)
    new_chat=gr.Button("🆕 New Chat")
    send.click(submit,[msg,chatbot,session],[msg,chatbot])
    msg.submit(submit,[msg,chatbot,session],[msg,chatbot])
    new_chat.click(new_session,outputs=session).then(lambda:[],outputs=chatbot)
if __name__=="__main__": demo.launch()
