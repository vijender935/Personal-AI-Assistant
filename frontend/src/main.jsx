import React,{useEffect,useState} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {createRoot} from "react-dom/client";
import {Menu,Plus,Search,Settings,User,Send,MessageSquare,Paperclip,Files,Trash2,Download,X,Copy,Check} from "lucide-react";
import FileUpload from "./components/FileUpload";
import "./styles.css";

const API=import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const initial=[{id:"new",title:"New conversation",messages:[]}];

function App(){
 const [chats,setChats]=useState(initial),[active,setActive]=useState("new"),[text,setText]=useState(""),[loading,setLoading]=useState(false),[sidebar,setSidebar]=useState(true),[settings,setSettings]=useState(false),[filesOpen,setFilesOpen]=useState(false),[files,setFiles]=useState([]),[fileQuery,setFileQuery]=useState(""),[user,setUser]=useState(null),[auth,setAuth]=useState({email:"",password:"",name:""}),[authMode,setAuthMode]=useState("login"),[attachments,setAttachments]=useState([]),[streamController,setStreamController]=useState(null),[chatQuery,setChatQuery]=useState(""),[copiedMessage,setCopiedMessage]=useState(null);
 const token=localStorage.getItem("personal_ai_token");
 const chat=chats.find(c=>c.id===active)||chats[0];

 useEffect(()=>{if(!token)return;fetch(API+"/api/v1/auth/me",{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(r.ok)setUser((await r.json()).user);else{localStorage.removeItem("personal_ai_token");setUser(null)}}).catch(()=>{});},[token]);
 useEffect(()=>{if(!token||!user)return;fetch(API+"/api/v1/chats",{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(!r.ok)return;const d=await r.json();if(d.chats?.length){setChats(d.chats);setActive(d.chats[0].session_id)}}).catch(()=>{});},[token,user]);

 async function loadFiles(){if(!token)return;const r=await fetch(API+"/api/v1/files",{headers:{Authorization:"Bearer "+token}});if(r.ok)setFiles((await r.json()).files||[]);}
 useEffect(()=>{if(user)loadFiles()},[user]);
 async function logout(){try{if(token)await fetch(API+"/api/v1/auth/logout",{method:"POST",headers:{Authorization:"Bearer "+token}})}catch(e){}localStorage.removeItem("personal_ai_token");setUser(null);setChats(initial);setActive("new");}
 async function authSubmit(){const path=authMode==="login"?"/api/v1/auth/login":"/api/v1/auth/register";const body=authMode==="login"?{email:auth.email,password:auth.password}:auth;const r=await fetch(API+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const d=await r.json();if(!r.ok){alert(d.detail||"Authentication failed");return}localStorage.setItem("personal_ai_token",d.token);setUser(d.user);}
 function update(messages){setChats(cs=>cs.map(c=>c.id===active?{...c,messages,title:c.title==="New conversation"?(messages.find(m=>m.role==="user")?.content||"New conversation").slice(0,32):c.title}:c));}
 async function regenerate(){
  if(loading||!chat.messages.length)return;
  const last=chat.messages[chat.messages.length-1];
  if(last.role!=="assistant")return;
  setLoading(true);
  try{
    const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(active)+"/regenerate",{method:"POST",headers:{Authorization:"Bearer "+token}});
    const d=await r.json();
    if(!r.ok){alert(d.detail||"Regeneration failed");return}
    update([...chat.messages.slice(0,-1),{role:"assistant",content:d.answer}]);
  }finally{setLoading(false)}
 }
 async function editLastUser(){
  if(loading||chat.messages.length<2)return;
  const userIndex=chat.messages.length-2;
  const old=chat.messages[userIndex];
  if(old.role!=="user")return;
  const message=prompt("Edit message",old.content);
  if(!message||message.trim()===old.content)return;
  setLoading(true);
  try{
    const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(active)+"/edit",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({message:message.trim(),session_id:active})});
    const d=await r.json();
    if(!r.ok){alert(d.detail||"Edit failed");return}
    update([...chat.messages.slice(0,userIndex),{role:"user",content:message.trim()},{role:"assistant",content:d.answer}]);
  }finally{setLoading(false)}
 }
 async function renameChat(id,currentTitle){
  const title=prompt("Rename chat",currentTitle);
  if(!title||title.trim()===currentTitle)return;
  const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(id),{method:"PATCH",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({title:title.trim()})});
  if(r.ok)setChats(cs=>cs.map(c=>c.id===id?{...c,title:title.trim()}:c));else alert("Rename failed");
 }
 async function deleteChatById(id){
  if(!confirm("Delete this chat?"))return;
  const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(id),{method:"DELETE",headers:{Authorization:"Bearer "+token}});
  if(!r.ok){alert("Delete failed");return}
  setChats(cs=>cs.filter(c=>c.id!==id));
  if(active===id){setActive(chats.find(c=>c.id!==id)?.id||"new")}
 }
 async function copyMessage(content,index){try{await navigator.clipboard.writeText(content);setCopiedMessage(index);setTimeout(()=>setCopiedMessage(null),1500)}catch(e){}}
 function newChat(){const id="web-"+Date.now();setChats(cs=>[{id,title:"New conversation",messages:[]},...cs]);setActive(id);setAttachments([]);}
 async function send(){
  const message=text.trim();if(!message||loading)return;
  const controller=new AbortController();setStreamController(controller);
  const next=[...chat.messages,{role:"user",content:message},{role:"assistant",content:""}];update(next);setText("");setLoading(true);
  try{
   const r=await fetch(API+"/api/v1/chat/stream",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({message,session_id:active,attachment_paths:attachments.map(a=>a.path)}),signal:controller.signal});
   if(!r.ok){const d=await r.json();update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:d.detail||"Request failed."}]);return}
   const reader=r.body.getReader(),decoder=new TextDecoder();let buffer="",answer="";
   while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const events=buffer.split("\n\n");buffer=events.pop()||"";for(const event of events){
     const type=event.split("\n").find(x=>x.startsWith("event:"))?.slice(6).trim()||"delta";
     const line=event.split("
").find(x=>x.startsWith("data: "));
     if(!line)continue;
     try{
       const p=JSON.parse(line.slice(6));
       if(type==="error"){throw new Error(p.detail||"Streaming failed.")}
       if(p.text){answer+=p.text;update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:answer}])}
     }catch(e){
       update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:e.message||"Streaming failed."}]);
       return;
     }
    }}
  }catch(e){if(e.name!=="AbortError")update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:"Backend se connection nahi ho paaya."}])}
  finally{setLoading(false);setStreamController(null);setAttachments([]);}
 }
 function stopStream(){streamController?.abort();setStreamController(null);setLoading(false);}
 async function uploadFile(file){const fd=new FormData();fd.append("file",file);const r=await fetch(API+"/api/v1/files/upload",{method:"POST",headers:{Authorization:"Bearer "+token},body:fd});const d=await r.json();if(!r.ok){alert(d.detail||"Upload failed");return}setAttachments(a=>[...a,{path:d.path,name:d.name}]);await loadFiles();}
 async function deleteFile(path){if(!confirm("Delete this file?"))return;const r=await fetch(API+"/api/v1/files/"+path.split("/").map(encodeURIComponent).join("/"),{method:"DELETE",headers:{Authorization:"Bearer "+token}});if(r.ok)await loadFiles();else alert("Delete failed");}
 async function downloadFile(path){const r=await fetch(API+"/api/v1/files/"+path.split("/").map(encodeURIComponent).join("/"),{headers:{Authorization:"Bearer "+token}});if(!r.ok){alert("Download failed");return}const blob=await r.blob();const url=URL.createObjectURL(blob);window.location.href=url;}

 if(!user&&!token)return <div className="auth-screen"><div className="auth-card"><div className="welcome-logo">✦</div><h1>{authMode==="login"?"Welcome back":"Create account"}</h1>{authMode==="register"&&<input placeholder="Name" value={auth.name} onChange={e=>setAuth({...auth,name:e.target.value})}/>}<input placeholder="Email" type="email" value={auth.email} onChange={e=>setAuth({...auth,email:e.target.value})}/><input placeholder="Password" type="password" value={auth.password} onChange={e=>setAuth({...auth,password:e.target.value})}/><button className="auth-submit" onClick={authSubmit}>{authMode==="login"?"Login":"Sign up"}</button><button className="auth-switch" onClick={()=>setAuthMode(authMode==="login"?"register":"login")}>{authMode==="login"?"Create an account":"Already have an account? Login"}</button></div></div>;

 return <div className="app">
  {sidebar&&<aside className="sidebar"><div className="brand"><div className="logo">✦</div>Personal AI Assistant<button onClick={()=>setSidebar(false)}><X size={18}/></button></div><button className="new" onClick={newChat}><Plus size={18}/>New chat</button><div className="search"><Search size={16}/><input placeholder="Search chats" value={chatQuery} onChange={e=>setChatQuery(e.target.value)}/></div><div className="chat-list">{chats.filter(c=>!chatQuery.trim()||c.title.toLowerCase().includes(chatQuery.toLowerCase())).map(c=><div className={"chat-row "+(c.id===active?"active":"")} key={c.id}><button className="chat" onClick={()=>setActive(c.id)}><MessageSquare size={16}/><span>{c.title}</span></button><button className="chat-more" title="Rename chat" onClick={()=>renameChat(c.id,c.title)}>✎</button><button className="chat-more" title="Delete chat" onClick={()=>deleteChatById(c.id)}>×</button></div>)}</div><div className="sidebar-bottom"><button onClick={()=>{setFilesOpen(true);loadFiles()}}><Files size={17}/>Files</button><button onClick={()=>setSettings(true)}><Settings size={17}/>Settings</button><button onClick={logout}><User size={17}/>Logout</button></div></aside>}
  <main className="main"><header>{!sidebar&&<button className="icon" onClick={()=>setSidebar(true)}><Menu size={20}/></button>}<div className="model">Personal AI <b>{user?.name||user?.email}</b></div><button className="avatar" onClick={()=>setSettings(true)}><User size={17}/></button></header>
   <section className="messages">{chat.messages.length===0?<div className="welcome"><div className="welcome-logo">✦</div><h1>How can I help?</h1><p>Your personal AI assistant</p></div>:chat.messages.map((m,i)=><div key={i} className={"bubble "+m.role}><div className="role">{m.role==="user"?"You":"Assistant"}</div><div className="message-content">{m.role==="assistant"?<ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>:m.content}</div><div className="message-actions"><button className="icon message-action" title="Copy message" onClick={()=>copyMessage(m.content,i)}>{copiedMessage===i?<Check size={14}/>:<Copy size={14}/>}</button>{i===chat.messages.length-1&&m.role==="assistant"&&<button className="icon message-action" title="Regenerate response" onClick={regenerate}>↻</button>}{i===chat.messages.length-2&&m.role==="user"&&chat.messages.at(-1)?.role==="assistant"&&<button className="icon message-action" title="Edit and resend" onClick={editLastUser}>✎</button>}</div></div>)}</section>
   <div className="composer-wrap"><div className="composer"><FileUpload onFile={uploadFile}/><textarea value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}}} placeholder="Message your assistant..." disabled={loading}/><button className="send" onClick={loading?stopStream:send} disabled={!loading&&!text.trim()}>{loading?"■":<Send size={18}/>}</button></div>{attachments.length>0&&<small>{attachments.map(a=>a.name).join(", ")}</small>}<small>AI can make mistakes. Check important information.</small></div>
  </main>
  {filesOpen&&<div className="overlay"><div className="settings"><div className="settings-head"><h2>Files</h2><button onClick={()=>setFilesOpen(false)}>×</button></div><input className="file-search" placeholder="Search files..." value={fileQuery} onChange={e=>setFileQuery(e.target.value)}/>{files.length===0?<p>No uploaded files.</p>:files.filter(f=>f.path.toLowerCase().includes(fileQuery.toLowerCase())).map(f=><div key={f.path} style={{display:"flex",alignItems:"center",gap:8,padding:"9px 0",borderBottom:"1px solid #eee"}}><Files size={16}/><span style={{flex:1,overflow:"hidden",textOverflow:"ellipsis"}}>{f.path}</span><small>{f.rag_indexed?"RAG ✓":"Not indexed"} · {Math.ceil(f.size/1024)} KB</small><button className="icon" onClick={()=>downloadFile(f.path)}><Download size={16}/></button><button className="icon" onClick={()=>deleteFile(f.path)}><Trash2 size={16}/></button></div>)}</div></div>}
  {settings&&<div className="overlay"><div className="settings"><div className="settings-head"><h2>Settings</h2><button onClick={()=>setSettings(false)}>×</button></div><p>Signed in as <b>{user?.email}</b></p><p>Model: server-configured Groq model</p></div></div>}
 </div>
}
createRoot(document.getElementById("root")).render(<App/>);
