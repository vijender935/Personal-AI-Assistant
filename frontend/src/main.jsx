import React,{useState} from "react";
import {createRoot} from "react-dom/client";
import {Menu,Plus,Search,Settings,User,Paperclip,Send,MessageSquare,PanelLeftClose} from "lucide-react";
import "./styles.css";

const API="http://127.0.0.1:8000";
const initial=[{id:1,title:"New conversation",messages:[]}];

function App(){
 const [chats,setChats]=useState(initial),[active,setActive]=useState(1),[text,setText]=useState(""),[loading,setLoading]=useState(false),[sidebar,setSidebar]=useState(true),[settings,setSettings]=useState(false);
 const chat=chats.find(c=>c.id===active)||chats[0];
 const update=(messages)=>setChats(cs=>cs.map(c=>c.id===active?{...c,messages,title:c.messages.length?c.title:(messages[0]?.content||"New conversation").slice(0,32)}:c));
 async function send(){
  const message=text.trim(); if(!message||loading)return;
  const next=[...chat.messages,{role:"user",content:message}]; update(next); setText(""); setLoading(true);
  try{
   const r=await fetch(API+"/api/v1/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message,session_id:"web-"+active})});
   const data=await r.json(); update([...next,{role:"assistant",content:r.ok?data.answer:(data.detail||"Request failed.")}]);
  }catch(e){update([...next,{role:"assistant",content:"Backend se connection nahi ho paaya. FastAPI server check karo."}]);}
  finally{setLoading(false);}
 }
 function newChat(){const id=Date.now();setChats(cs=>[{id,title:"New conversation",messages:[]},...cs]);setActive(id);}
 return <div className="app">
  {sidebar&&<aside className="sidebar">
   <div className="brand"><div className="logo">✦</div><span>Personal AI</span><button onClick={()=>setSidebar(false)}><PanelLeftClose size={18}/></button></div>
   <button className="new" onClick={newChat}><Plus size={18}/>New chat</button>
   <div className="search"><Search size={16}/><input placeholder="Search chats"/></div>
   <div className="chat-list">{chats.map(c=><button className={c.id===active?"chat active":"chat"} key={c.id} onClick={()=>setActive(c.id)}><MessageSquare size={16}/><span>{c.title}</span></button>)}</div>
   <div className="sidebar-bottom"><button onClick={()=>setSettings(true)}><Settings size={18}/>Settings</button><button><User size={18}/>Profile</button></div>
  </aside>}
  <main className="main">
   <header><button className="icon" onClick={()=>setSidebar(true)}><Menu size={20}/></button><span className="model">Personal AI <b>GPT-OSS 120B</b></span><button className="avatar">V</button></header>
   <section className="messages">
    {chat.messages.length===0?<div className="welcome"><div className="welcome-logo">✦</div><h1>How can I help you?</h1><p>Your personal AI assistant for conversation, knowledge and tools.</p><div className="suggestions"><button onClick={()=>setText("Explain my project architecture")}>Explain my project</button><button onClick={()=>setText("Search my knowledge base")}>Search knowledge</button><button onClick={()=>setText("Help me write Python code")}>Write Python code</button></div></div>:
     chat.messages.map((m,i)=><div className={m.role==="user"?"bubble user":"bubble assistant"} key={i}><div className="role">{m.role==="user"?"You":"Personal AI"}</div><div>{m.content}</div></div>)}
    {loading&&<div className="bubble assistant"><div className="role">Personal AI</div><div className="typing"><i/><i/><i/></div></div>}
   </section>
   <div className="composer-wrap"><div className="composer"><button className="icon"><Paperclip size={19}/></button><textarea value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}}} placeholder="Message Personal AI..." rows="1"/><button className="send" onClick={send} disabled={!text.trim()||loading}><Send size={18}/></button></div><small>Personal AI can make mistakes. Verify important information.</small></div>
  </main>
  {settings&&<div className="overlay" onClick={()=>setSettings(false)}><div className="settings" onClick={e=>e.stopPropagation()}><div className="settings-head"><h2>Settings</h2><button onClick={()=>setSettings(false)}>×</button></div><label>API endpoint<input value={API} readOnly/></label><label>Appearance<select defaultValue="system"><option>System</option><option>Light</option><option>Dark</option></select></label><label>Model<input value="openai/gpt-oss-120b" readOnly/></label></div></div>}
 </div>
}
createRoot(document.getElementById("root")).render(<App/>);