"""Personal AI Agent — conversational + persistent memory + local tools."""
from __future__ import annotations
import json,logging,os,sys,time
from typing import Optional
from groq import Groq
from config import MAX_HISTORY_MESSAGES,MAX_ITERATIONS,MAX_RETRIES,MODEL,VISION_MODEL
from tools import TOOL_FUNCTIONS,TOOL_SCHEMAS,init_db,load_history,semantic_recall_memories,remember_fact,save_turn
logger=logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO").upper(),format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
SYSTEM_PROMPT="""Tum ek helpful personal AI assistant ho.
User se natural Hinglish me baat karo.
Context ko yaad rakho aur previous conversation ko use karo.
Jab current information, calculation, file operation ya shell task ki zaroorat ho, appropriate tool use karo.
Tool results ko clearly explain karo. Kabhi bhi tool result invent mat karo.
Dangerous/destructive local actions se bacho."""
def _extract_memory_candidate(text):
    lower=text.lower().strip();prefixes=("remember that ","yaad rakhna ","yaad rakho ","note that ","remember: ","yaad rakho:")
    for prefix in prefixes:
        if lower.startswith(prefix):return text.strip()[len(prefix):].strip()
    return None
def build_messages(goal,session_id,user_id=0,rag_sources=None):
    history=load_history(session_id,MAX_HISTORY_MESSAGES,user_id=user_id);memories=semantic_recall_memories(goal,limit=8,user_id=user_id)
    messages=[{"role":"system","content":SYSTEM_PROMPT}]
    if memories:messages.append({"role":"system","content":"Relevant saved memories (semantic retrieval):\n"+"\n".join(f"- {m}" for m in memories)})
    try:
        from memory import search_rag
        rag_results=search_rag(goal,limit=4,user_id=user_id,sources=rag_sources)
    except Exception:rag_results=[]
    if rag_results:
        context="\n\n".join(f"[{item['source']} | score={item['score']}]\n{item['content']}" for item in rag_results)
        messages.append({"role":"system","content":"Relevant knowledge-base context:\n"+context})
    messages.extend(history);messages.append({"role":"user","content":goal});return messages
def run_agent(goal,session_id="default",user_id=0,image_urls=None,rag_sources=None,verbose=True):
    goal=goal.strip()
    if not goal:return "Please enter a message."
    api_key=os.getenv("GROQ_API_KEY")
    if not api_key:return "❌ GROQ_API_KEY set nahi hai. README.md dekho setup ke liye."
    explicit_memory=_extract_memory_candidate(goal)
    if explicit_memory:
        remember_fact(explicit_memory,source="user-explicit",user_id=user_id)
        try:
            from memory import remember_semantic
            remember_semantic(explicit_memory,source="user-explicit",user_id=user_id)
        except Exception as exc:logger.warning("Semantic memory unavailable: %s",exc)
    client,messages=Groq(api_key=api_key),build_messages(goal,session_id,user_id=user_id,rag_sources=rag_sources)
    mcp_schemas=[]
    try:
        from mcp_client import discover_tool_schemas
        mcp_schemas=discover_tool_schemas()
    except Exception as exc:
        logger.warning("MCP discovery unavailable: %s",exc)
    tool_schemas=TOOL_SCHEMAS+mcp_schemas
    if image_urls:
        messages[-1]["content"]=[{"type":"text","text":goal}]+[{"type":"image_url","image_url":{"url":url}} for url in image_urls]
    for _ in range(MAX_ITERATIONS):
        response=None
        for retry in range(MAX_RETRIES+1):
            try:
                response=client.chat.completions.create(model=VISION_MODEL if image_urls else MODEL,messages=messages,tools=tool_schemas,tool_choice="auto",temperature=0.4);break
            except Exception as exc:
                logger.warning("Model request failed (retry %s): %s",retry,exc)
                if retry<MAX_RETRIES:time.sleep(2**retry)
        if response is None:return "❌ Model/API request failed after retries. Logs me details available hain."
        msg=response.choices[0].message;messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            answer=msg.content or "";save_turn(session_id,goal,answer,user_id=user_id);return answer
        for call in msg.tool_calls:
            name=call.function.name
            try:args=json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:args={}
            if verbose:logger.info("Tool call: %s(%s)",name,args)
            fn=TOOL_FUNCTIONS.get(name)
            try:
                if fn:
                    result=fn(**args)
                elif name.startswith("mcp__"):
                    from mcp_client import call_tool
                    result=call_tool(name,args)
                else:
                    result=f"Unknown tool: {name}"
            except Exception as exc:
                logger.exception("Tool failed: %s",name)
                result=f"Tool error in {name}: {exc}"
            messages.append({"role":"tool","tool_call_id":call.id,"name":name,"content":str(result)})
    return f"⚠️ Max tool iterations ({MAX_ITERATIONS}) reached — task incomplete reh gaya."
def stream_agent(goal,session_id="default",user_id=0,image_urls=None,rag_sources=None):
    """Yield assistant text chunks using Groq streaming.

    Tool execution remains available through the normal /chat endpoint. Streaming
    is intentionally used for direct model responses so tool-call semantics stay
    deterministic.
    """
    goal=goal.strip()
    if not goal:
        yield "Please enter a message."
        return
    api_key=os.getenv("GROQ_API_KEY")
    if not api_key:
        yield "❌ GROQ_API_KEY set nahi hai."
        return
    messages=build_messages(goal,session_id,user_id=user_id,rag_sources=rag_sources)
    if image_urls:
        messages[-1]["content"]=[{"type":"text","text":goal}]+[
            {"type":"image_url","image_url":{"url":url}} for url in image_urls
        ]
    client=Groq(api_key=api_key)
    try:
        stream=client.chat.completions.create(
            model=VISION_MODEL if image_urls else MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="none",
            temperature=0.4,
            stream=True,
        )
        parts=[]
        for chunk in stream:
            delta=chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                parts.append(delta)
                yield delta
        answer="".join(parts)
        if answer:
            save_turn(session_id,goal,answer,user_id=user_id)
    except Exception as exc:
        logger.exception("Streaming model request failed")
        yield f"❌ Streaming request failed: {exc}"


def interactive():
    session_id=os.getenv("AGENT_SESSION","default");print(f"Personal AI Agent — model: {MODEL}");print("Commands: /new, /remember <fact>, /memories, /exit\n")
    while True:
        try:goal=input("Tum: ").strip()
        except (EOFError,KeyboardInterrupt):print();break
        if not goal:continue
        command=goal.lower()
        if command in {"/exit","/quit","exit","quit"}:break
        if command=="/new":session_id=f"session-{time.time_ns()}";print(f"🆕 New session: {session_id}\n");continue
        if command=="/memories":print("\n".join(f"- {m}" for m in recall_memories("",limit=50,user_id=0)) or "(no memories)");print();continue
        if command.startswith("/remember "):remember_fact(goal[len("/remember "):].strip(),source="user-command",user_id=0);print("🧠 Memory saved.\n");continue
        print("\nAgent:",run_agent(goal,session_id=session_id,user_id=0),"\n")
if __name__=="__main__":
    init_db()
    print(run_agent(" ".join(sys.argv[1:]))) if len(sys.argv)>1 else interactive()
