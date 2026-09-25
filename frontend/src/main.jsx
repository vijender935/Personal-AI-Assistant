import React,{useEffect,useState} from "react";
import {createRoot} from "react-dom/client";
import {Menu,Plus,Search,Settings,User,Send,MessageSquare,PanelLeftClose} from "lucide-react";
import FileUpload from "./components/FileUpload";
import "./styles.css";

const API=import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const initial=[{id:1,title:"New conversation",messages:[]}];

function App(){
 const [chats,setChats]=useState(initial),[active,setActive]=useState(1),[text,setText]=useState(""),[loading,setLoading]=useState(false),[sidebar,setSidebar]=useState(true),[settings,setSettings]=useState(false),[user,setUser]=useState(null),[auth,setAuth]=useState({email:"",password:"",name:""}),[authMode,setAuthMode]=useState("login"),[attachments,setAttachments]=useState([]);
 const chat=chats.find(c=>c.id===active)||chats[0];
 const token=localStorage.getItem("personal_ai_token");
 useEffect(()=>{if(!token)return;fetch(API+"/api/v1/auth/me",{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(r.ok){const d=await r.json();setUser(d.user)}else{localStorage.removeItem("personal_ai_token");setUser(null)}}).catch(()=>{});},[token]);
 useEffect(()=>{if(!token||!user)return;fetch(API+"/api/v1/chats",{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(!r.ok)return;const d=await r.json();if(d.chats?.length){setChats(d.chats.map(c=>({id:c.session_id,title:c.title||"New conversation",messages:c.messages||[]})));setActive(d.chats[0].session_id);}}).catch(()=>{});},[token,user]);
 useEffect(()=>{if(!token||!user||!active)return;fetch(API+"/api/v1/chats/"+encodeURIComponent(active),{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(!r.ok)return;const d=await r.json();setChats(cs=>cs.map(c=>c.id===active?{...c,messages:d.messages||[]}:c));}).catch(()=>{});},[active,token,user]);
 async function logout(){if(token){try{await fetch(API+"/api/v1/auth/logout",{method:"POST",headers:{Authorization:"Bearer "+token}})}catch(e){}}localStorage.removeItem("personal_ai_token");setUser(null);setChats(initial);setActive(1);setSettings(false);}
 async function loadMcp(){if(!token)return;const r=await fetch(API+"/api/v1/mcp/servers",{headers:{Authorization:"Bearer "+token}});if(r.ok){const d=await r.json();alert(d.servers.length?d.servers.map(s=>s.name+" ("+s.transport+")").join("\\n"):"No MCP servers configured.");}}
 async function authSubmit(){const path=authMode==="login"?"/api/v1/auth/login":"/api/v1/auth/register";const body=authMode==="login"?{email:auth.email,password:auth.password}:auth;const r=await fetch(API+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const d=await r.json();if(!r.ok){alert(d.detail||"Authentication failed");return;}localStorage.setItem("personal_ai_token",d.token);setUser(d.user);}
 if(!user&&!token)return <div className="auth-screen"><div className="auth-card"><div className="welcome-logo">✦</div><h1>{authMode==="login"?"Welcome back":"Create account"}</h1>{authMode==="register"&&<input placeholder="Name" value={auth.name} onChange={e=>setAuth({...auth,name:e.target.value})}/>}<input placeholder="Email" type="email" value={auth.email} onChange={e=>setAuth({...auth,email:e.target.value})}/><input placeholder="Password" type="password" value={auth.password} onChange={e=>setAuth({...auth,password:e.target.value})}/><button className="auth-submit" onClick={authSubmit}>{authMode==="login"?"Login":"Sign up"}</button><button className="auth-switch" onClick={()=>setAuthMode(authMode==="login"?"register":"login")}>{authMode==="login"?"Create an account":"Already have an account? Login"}</button></div></div>;
 const update=(messages)=>setChats(cs=>cs.map(c=>c.id===active?{...c,messages,title:c.messages.length?c.title:(messages[0]?.content||"New conversation").slice(0,32)}:c));
 async function send(){
  const message=text.trim(); if(!message||loading)return;
  const next=[...chat.messages,{role:"user",content:message}]; update(next); setText(""); setLoading(true);
  try{
   const r=await fetch(API+"/api/v1/chat",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({message,session_id:"web-"+active,attachment_paths:attachments.map(a=>a.path)})});
   const data=await r.json(); update([...next,{role:"assistant",content:r.ok?data.answer:(data.detail||"Request failed.")}]);
  }catch(e){update([...next,{role:"assistant",content:"Backend se connection nahi ho paaya. FastAPI server check karo."}]);}
  finally{setLoading(false);}
 }
 function newChat(){const id="web-"+Date.now();setChats(cs=>[{id,title:"New conversation",messages:[]},...cs]);setActive(id);}
 return <div className="app">
  {sidebar&&<aside className="sidebar">
   <div className="brand"><div className="logo">✦</div><span>Personal AI</span><button onClick={()=>setSidebar(false)}><PanelLeftClose size={18}/></button></div>
   <button className="new" onClick={newChat}><Plus size={18}/>New chat</button>
   <div className="search"><Search size={16}/><input placeholder="Search chats"/></div>
   <div className="chat-list">{chats.map(c=><button className={c.id===active?"chat active":"chat"} key={c.id} onClick={()=>setActive(c.id)}><MessageSquare size={16}/><span>{c.title}</span></button>)}</div>
   <div className="sidebar-bottom"><button onClick={()=>setSettings(true)}><Settings size={18}/>Settings</button><button onClick={loadMcp}><MessageSquare size={18}/>MCP Servers</button><button onClick={()=>setSettings(true)}><User size={18}/>Profile</button><button onClick={logout}>Logout</button></div>
  </aside>}
  <main className="main">
   <header><button className="icon" onClick={()=>setSidebar(true)}><Menu size={20}/></button><span className="model">Personal AI <b>GPT-OSS 120B</b></span><button className="avatar" onClick={()=>setSettings(true)}>{user?.name?.[0]?.toUpperCase()||"V"}</button></header>
   <section className="messages">
    {chat.messages.length===0?<div className="welcome"><div className="welcome-logo">✦</div><h1>How can I help you?</h1><p>Your personal AI assistant for conversation, knowledge and tools.</p><div className="suggestions"><button onClick={()=>setText("Explain my project architecture")}>Explain my project</button><button onClick={()=>setText("Search my knowledge base")}>Search knowledge</button><button onClick={()=>setText("Help me write Python code")}>Write Python code</button></div></div>:
     chat.messages.map((m,i)=><div className={m.role==="user"?"bubble user":"bubble assistant"} key={i}><div className="role">{m.role==="user"?"You":"Personal AI"}</div><div>{m.content}</div></div>)}
    {loading&&<div className="bubble assistant"><div className="role">Personal AI</div><div className="typing"><i/><i/><i/></div></div>}
   </section>
   <div className="composer-wrap"><div className="composer"><FileUpload onFile={async file=>{if(!token){alert("Login required");return;}const fd=new FormData();fd.append("file",file);const r=await fetch(API+"/api/v1/files/upload",{method:"POST",headers:{Authorization:"Bearer "+token},body:fd});const d=await r.json();if(!r.ok){alert(d.detail||"Upload failed");return;}setAttachments(xs=>[...xs.slice(-2),{path:d.path,name:d.filename,indexed:d.indexed_chunks||0}]);}}/><div className="attachments">{attachments.map(a=><span key={a.path}>{a.name}{a.indexed?` · ${a.indexed} chunks`:""} <button onClick={()=>setAttachments(xs=>xs.filter(x=>x.path!==a.path))}>×</button></span>)}</div><textarea value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}}} placeholder="Message Personal AI..." rows="1"/><button className="send" onClick={send} disabled={!text.trim()||loading}><Send size={18}/></button></div><small>Personal AI can make mistakes. Verify important information.</small></div>
  </main>
  {settings&&<div className="overlay" onClick={()=>setSettings(false)}><div className="settings" onClick={e=>e.stopPropagation()}><div className="settings-head"><h2>Settings</h2><button onClick={()=>setSettings(false)}>×</button></div><label>API endpoint<input value={API} readOnly/></label><label>Appearance<select defaultValue="system"><option>System</option><option>Light</option><option>Dark</option></select></label><label>Model<input value="openai/gpt-oss-120b" readOnly/></label><label>Account<input value={user?.email||""} readOnly/></label><button className="auth-submit" onClick={logout}>Logout</button></div></div>}
 </div>
}
createRoot(document.getElementById("root")).render(<App/>);