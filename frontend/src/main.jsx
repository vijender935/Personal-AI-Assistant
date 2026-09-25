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
 const [chats,setChats]=useState(initial),[active,setActive]=useState("new"),[text,setText]=useState(""),[loading,setLoading]=useState(false),[sidebar,setSidebar]=useState(true),[settings,setSettings]=useState(false),[filesOpen,setFilesOpen]=useState(false),[files,setFiles]=useState([]),[fileQuery,setFileQuery]=useState(""),[user,setUser]=useState(null),[auth,setAuth]=useState({email:"",password:"",name:""}),[authMode,setAuthMode]=useState("login"),[attachments,setAttachments]=useState([]),[streamController,setStreamController]=useState(null),[chatQuery,setChatQuery]=useState(""),[copiedMessage,setCopiedMessage]=useState(null),[connectors,setConnectors]=useState([]),[connectorForm,setConnectorForm]=useState({name:"",transport:"streamable-http",url:"",allowed_tools:""}),[connectorLoading,setConnectorLoading]=useState(false),[memories,setMemories]=useState([]),[memoryForm,setMemoryForm]=useState(""),[memoryOpen,setMemoryOpen]=useState(false),[toast,setToast]=useState(null),[confirmState,setConfirmState]=useState(null),[editState,setEditState]=useState(null),[renameState,setRenameState]=useState(null),[uploading,setUploading]=useState(false);
 const token=localStorage.getItem("personal_ai_token");
 const chat=chats.find(c=>c.id===active)||chats[0];
 function notify(message,type="error"){setToast({message,type});window.clearTimeout(notify.timer);notify.timer=window.setTimeout(()=>setToast(null),3200)}

 useEffect(()=>{if(!token)return;fetch(API+"/api/v1/auth/me",{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(r.ok)setUser((await r.json()).user);else{localStorage.removeItem("personal_ai_token");setUser(null)}}).catch(()=>{});},[token]);
 useEffect(()=>{if(!token||!user)return;fetch(API+"/api/v1/chats",{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(!r.ok)return;const d=await r.json();if(d.chats?.length){const normalized=d.chats.map(c=>({...c,id:c.session_id}));setChats(normalized);setActive(normalized[0].id)}}).catch(()=>{});},[token,user]);
 useEffect(()=>{if(!token||!user||!active||active==="new")return;let cancelled=false;fetch(API+"/api/v1/chats/"+encodeURIComponent(active),{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(!r.ok)return;const d=await r.json();if(cancelled)return;setChats(cs=>cs.map(c=>c.id===active?{...c,messages:d.messages||[]}:c));}).catch(()=>{});return()=>{cancelled=true}},[active,token,user]);

 async function loadFiles(){if(!token)return;const r=await fetch(API+"/api/v1/files",{headers:{Authorization:"Bearer "+token}});if(r.ok)setFiles((await r.json()).files||[]);}
 async function loadMemories(){if(!token)return;const r=await fetch(API+"/api/v1/memories",{headers:{Authorization:"Bearer "+token}});if(r.ok)setMemories((await r.json()).memories||[]);}
 async function saveMemory(){const fact=memoryForm.trim();if(!fact)return;const r=await fetch(API+"/api/v1/memories",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({fact,source:"settings"})});if(!r.ok){const d=await r.json();notify(d.detail||"Memory save failed");return}setMemoryForm("");await loadMemories();}
 async function deleteMemory(fact){const r=await fetch(API+"/api/v1/memories?fact="+encodeURIComponent(fact),{method:"DELETE",headers:{Authorization:"Bearer "+token}});if(r.ok)setMemories(ms=>ms.filter(x=>x!==fact));else notify("Memory delete failed");}
 async function loadConnectors(){if(!token)return;const r=await fetch(API+"/api/v1/mcp/connectors",{headers:{Authorization:"Bearer "+token}});if(r.ok)setConnectors((await r.json()).connectors||[]);}
 async function addConnector(){if(connectorLoading)return;setConnectorLoading(true);try{const r=await fetch(API+"/api/v1/mcp/connectors",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({name:connectorForm.name.trim(),transport:connectorForm.transport,url:connectorForm.url.trim(),allowed_tools:connectorForm.allowed_tools.split(",").map(x=>x.trim()).filter(Boolean)})});const d=await r.json();if(!r.ok){notify(d.detail||"Connector add failed");return}setConnectors(cs=>[...cs.filter(x=>x.id!==d.connector.id),d.connector]);setConnectorForm({name:"",transport:"streamable-http",url:"",allowed_tools:""});}finally{setConnectorLoading(false)}}
 async function deleteConnectorById(id){const r=await fetch(API+"/api/v1/mcp/connectors/"+id,{method:"DELETE",headers:{Authorization:"Bearer "+token}});if(r.ok)setConnectors(cs=>cs.filter(x=>x.id!==id));else notify("Connector delete failed");}
 useEffect(()=>{if(user){loadFiles();loadConnectors();loadMemories()}},[user]);
 async function logout(){try{if(token)await fetch(API+"/api/v1/auth/logout",{method:"POST",headers:{Authorization:"Bearer "+token}})}catch(e){}localStorage.removeItem("personal_ai_token");setUser(null);setChats(initial);setActive("new");}
 async function authSubmit(){const path=authMode==="login"?"/api/v1/auth/login":"/api/v1/auth/register";const body=authMode==="login"?{email:auth.email,password:auth.password}:auth;const r=await fetch(API+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const d=await r.json();if(!r.ok){notify(d.detail||"Authentication failed");return}localStorage.setItem("personal_ai_token",d.token);setUser(d.user);}
 function update(messages){setChats(cs=>cs.map(c=>c.id===active?{...c,messages,title:c.title==="New conversation"?(messages.find(m=>m.role==="user")?.content||"New conversation").slice(0,32):c.title}:c));}
 async function regenerate(){
  if(loading||!chat.messages.length)return;
  const last=chat.messages[chat.messages.length-1];
  if(last.role!=="assistant")return;
  setLoading(true);
  try{
    const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(active)+"/regenerate",{method:"POST",headers:{Authorization:"Bearer "+token}});
    const d=await r.json();
    if(!r.ok){notify(d.detail||"Regeneration failed");return}
    update([...chat.messages.slice(0,-1),{role:"assistant",content:d.answer}]);
  }finally{setLoading(false)}
 }
 function editLastUser(){
  if(loading||chat.messages.length<2)return;
  const userIndex=chat.messages.length-2;
  const old=chat.messages[userIndex];
  if(old.role!=="user")return;
  setEditState({value:old.content,index:userIndex});
 }
 async function renameChat(id,currentTitle){
  setRenameState({id,value:currentTitle});
 }
 async function submitRename(){
  const {id,value}=renameState||{}; const title=value?.trim();
  if(!id||!title){notify("Chat name cannot be empty");return} 
  if(title===chats.find(c=>c.id===id)?.title){setRenameState(null);return}
  const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(id),{method:"PATCH",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({title:title.trim()})});
  if(r.ok){setChats(cs=>cs.map(c=>c.id===id?{...c,title}:c));setRenameState(null)}else notify("Rename failed");
 }
 async function deleteChatById(id){
  setConfirmState({type:"chat",id,message:"Delete this conversation?"});
 }
 async function confirmDeleteChat(id){
  const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(id),{method:"DELETE",headers:{Authorization:"Bearer "+token}});
  if(!r.ok){notify("Delete failed");return}
  const remaining=chats.filter(c=>c.id!==id);
  setChats(remaining.length?remaining:[{id:"new",title:"New conversation",messages:[]}]);
  if(active===id)setActive(remaining[0]?.id||"new");
 }
 async function copyMessage(content,index){try{await navigator.clipboard.writeText(content);setCopiedMessage(index);setTimeout(()=>setCopiedMessage(null),1500)}catch(e){}}
 function newChat(){const id="web-"+Date.now();setChats(cs=>[{id,title:"New conversation",messages:[]},...cs]);setActive(id);setAttachments([]);if(window.innerWidth<701)setSidebar(false)}
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
     const line=event.split("\n").find(x=>x.startsWith("data: "));
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
 async function uploadFile(file){setUploading(true);try{const fd=new FormData();fd.append("file",file);const r=await fetch(API+"/api/v1/files/upload",{method:"POST",headers:{Authorization:"Bearer "+token},body:fd});const d=await r.json();if(!r.ok){notify(d.detail||"Upload failed");return}setAttachments(a=>[...a,{path:d.path,name:d.name}]);await loadFiles();notify("File attached","success")}catch(e){notify("Upload failed")}finally{setUploading(false)}}
 async function deleteFile(path){setConfirmState({type:"file",path,message:"Delete this file? This also removes its indexed content."});}
 async function confirmDeleteFile(path){const r=await fetch(API+"/api/v1/files/"+path.split("/").map(encodeURIComponent).join("/"),{method:"DELETE",headers:{Authorization:"Bearer "+token}});if(r.ok)await loadFiles();else notify("Delete failed");}
 async function downloadFile(path){const r=await fetch(API+"/api/v1/files/"+path.split("/").map(encodeURIComponent).join("/"),{headers:{Authorization:"Bearer "+token}});if(!r.ok){notify("Download failed");return}const blob=await r.blob();const url=URL.createObjectURL(blob);window.location.href=url;}

 if(!user&&!token)return <div className="auth-screen"><div className="auth-card"><div className="welcome-logo">✦</div><h1>{authMode==="login"?"Welcome back":"Create account"}</h1>{authMode==="register"&&<input placeholder="Name" value={auth.name} onChange={e=>setAuth({...auth,name:e.target.value})}/>}<input placeholder="Email" type="email" value={auth.email} onChange={e=>setAuth({...auth,email:e.target.value})}/><input placeholder="Password" type="password" value={auth.password} onChange={e=>setAuth({...auth,password:e.target.value})}/><button className="auth-submit" onClick={authSubmit}>{authMode==="login"?"Login":"Sign up"}</button><button className="auth-switch" onClick={()=>setAuthMode(authMode==="login"?"register":"login")}>{authMode==="login"?"Create an account":"Already have an account? Login"}</button></div></div>;

 return <div className="app">
  {sidebar&&<><div className="sidebar-backdrop" onClick={()=>setSidebar(false)}/><aside className="sidebar"><div className="brand"><div className="logo">✦</div>Personal AI Assistant<button onClick={()=>setSidebar(false)}><X size={18}/></button></div><button className="new" onClick={newChat}><Plus size={18}/>New chat</button><div className="search"><Search size={16}/><input placeholder="Search chats" value={chatQuery} onChange={e=>setChatQuery(e.target.value)}/></div><div className="chat-list">{chats.filter(c=>!chatQuery.trim()||c.title.toLowerCase().includes(chatQuery.toLowerCase())).map(c=><div className={"chat-row "+(c.id===active?"active":"")} key={c.id}><button className="chat" onClick={()=>{setActive(c.id);if(window.innerWidth<701)setSidebar(false)}}><MessageSquare size={16}/><span>{c.title}</span></button><button className="chat-more" title="Rename chat" onClick={()=>renameChat(c.id,c.title)}>✎</button><button className="chat-more" title="Delete chat" onClick={()=>deleteChatById(c.id)}>×</button></div>)}</div><div className="sidebar-bottom"><button onClick={()=>{setFilesOpen(true);loadFiles()}}><Files size={17}/>Files</button><button onClick={()=>{setMemoryOpen(true);loadMemories()}}><User size={17}/>Memory</button><button onClick={()=>setSettings(true)}><Settings size={17}/>Settings</button><button onClick={logout}><User size={17}/>Logout</button></div></aside></>}
  <main className="main"><header>{!sidebar&&<button className="icon" onClick={()=>setSidebar(true)}><Menu size={20}/></button>}<div className="model">Personal AI <b>{user?.name||user?.email}</b></div><button className="avatar" onClick={()=>setSettings(true)}><User size={17}/></button></header>
   <section className="messages">{chat.messages.length===0?<div className="welcome"><div className="welcome-logo">✦</div><h1>How can I help?</h1><p>Your personal AI assistant</p></div>:chat.messages.map((m,i)=><div key={i} className={"bubble "+m.role}><div className="role">{m.role==="user"?"You":"Assistant"}</div><div className="message-content">{m.role==="assistant"?(m.content?<ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>:loading&&i===chat.messages.length-1?<div className="typing" aria-label="Assistant is thinking"><i></i><i></i><i></i></div>:null):m.content}</div><div className="message-actions"><button className="icon message-action" title="Copy message" onClick={()=>copyMessage(m.content,i)}>{copiedMessage===i?<Check size={14}/>:<Copy size={14}/>}</button>{i===chat.messages.length-1&&m.role==="assistant"&&<button className="icon message-action" title="Regenerate response" onClick={regenerate}>↻</button>}{i===chat.messages.length-2&&m.role==="user"&&chat.messages.at(-1)?.role==="assistant"&&<button className="icon message-action" title="Edit and resend" onClick={editLastUser}>✎</button>}</div></div>)}</section>
   <div className="composer-wrap"><div className="composer"><FileUpload onFile={uploadFile}/><textarea value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}}} placeholder="Message your assistant..." disabled={loading}/><button className="send" onClick={loading?stopStream:send} disabled={!loading&&!text.trim()}>{loading?"■":<Send size={18}/>}</button></div>{attachments.length>0&&<div className="attachments">{attachments.map(a=><span className="attachment" key={a.path}><Paperclip size={12}/>{a.name}<button onClick={()=>setAttachments(xs=>xs.filter(x=>x.path!==a.path))}><X size={12}/></button></span>)}</div>}{uploading&&<small className="uploading">Uploading file…</small>}<small>AI can make mistakes. Check important information.</small></div>
  </main>
  {toast&&<div className={"toast "+toast.type}>{toast.message}</div>}
  {confirmState&&<div className="overlay"><div className="confirm-card"><h3>Are you sure?</h3><p>{confirmState.message}</p><div className="modal-actions"><button className="secondary" onClick={()=>setConfirmState(null)}>Cancel</button><button className="danger" onClick={async()=>{const x=confirmState;if(x.type==="chat")await confirmDeleteChat(x.id);else await confirmDeleteFile(x.path);setConfirmState(null)}}>Delete</button></div></div></div>}
  {editState&&<div className="overlay"><div className="confirm-card"><div className="settings-head"><h3>Edit message</h3><button onClick={()=>setEditState(null)}>×</button></div><textarea className="modal-textarea" value={editState.value} onChange={e=>setEditState({...editState,value:e.target.value})}/><div className="modal-actions"><button className="secondary" onClick={()=>setEditState(null)}>Cancel</button><button className="primary" onClick={async()=>{const message=editState.value.trim();if(!message){notify("Message cannot be empty");return}const userIndex=editState.index;setEditState(null);setLoading(true);try{const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(active)+"/edit",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({message,session_id:active})});const d=await r.json();if(!r.ok){notify(d.detail||"Edit failed");return}update([...chat.messages.slice(0,userIndex),{role:"user",content:message},{role:"assistant",content:d.answer}])}finally{setLoading(false)}}}>Save & resend</button></div></div></div>}
  {renameState&&<div className="overlay"><div className="confirm-card"><div className="settings-head"><h3>Rename chat</h3><button onClick={()=>setRenameState(null)}>×</button></div><input className="modal-input" autoFocus value={renameState.value} onChange={e=>setRenameState({...renameState,value:e.target.value})} onKeyDown={e=>{if(e.key==="Enter")submitRename()}}/><div className="modal-actions"><button className="secondary" onClick={()=>setRenameState(null)}>Cancel</button><button className="primary" onClick={submitRename}>Rename</button></div></div></div>}
  {filesOpen&&<div className="overlay"><div className="settings"><div className="settings-head"><h2>Files</h2><button onClick={()=>setFilesOpen(false)}>×</button></div><input className="file-search" placeholder="Search files..." value={fileQuery} onChange={e=>setFileQuery(e.target.value)}/>{files.length===0?<p>No uploaded files.</p>:files.filter(f=>f.path.toLowerCase().includes(fileQuery.toLowerCase())).map(f=><div key={f.path} style={{display:"flex",alignItems:"center",gap:8,padding:"9px 0",borderBottom:"1px solid #eee"}}><Files size={16}/><span style={{flex:1,overflow:"hidden",textOverflow:"ellipsis"}}>{f.path}</span><small>{f.rag_indexed?"RAG ✓":"Not indexed"} · {Math.ceil(f.size/1024)} KB</small><button className="icon" onClick={()=>downloadFile(f.path)}><Download size={16}/></button><button className="icon" onClick={()=>deleteFile(f.path)}><Trash2 size={16}/></button></div>)}</div></div>}
  {memoryOpen&&<div className="overlay"><div className="settings settings-large"><div className="settings-head"><h2>Memory</h2><button onClick={()=>setMemoryOpen(false)}>×</button></div><p>Your saved assistant memories.</p><div className="connector-form"><input placeholder="Remember something..." value={memoryForm} onChange={e=>setMemoryForm(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();saveMemory()}}}/><button className="auth-submit" onClick={saveMemory}>Save memory</button></div><div className="connector-list">{memories.length===0?<p>No saved memories.</p>:memories.map((m,i)=><div className="connector-item" key={i}><div><span>{m}</span></div><button className="chat-more" onClick={()=>deleteMemory(m)}>Delete</button></div>)}</div></div></div>}
  {settings&&<div className="overlay"><div className="settings settings-large"><div className="settings-head"><h2>Settings</h2><button onClick={()=>setSettings(false)}>×</button></div><p>Signed in as <b>{user?.email}</b></p><p>Model: server-configured Groq model</p><hr/><h3>MCP & Connectors</h3><p className="settings-note">Yahan apna remote MCP server add karo. Abhi HTTP/SSE connectors supported hain.</p><div className="connector-form"><input placeholder="Name (e.g. GitHub)" value={connectorForm.name} onChange={e=>setConnectorForm({...connectorForm,name:e.target.value})}/><select value={connectorForm.transport} onChange={e=>setConnectorForm({...connectorForm,transport:e.target.value})}><option value="streamable-http">Streamable HTTP</option><option value="sse">SSE</option></select><input placeholder="MCP server URL" value={connectorForm.url} onChange={e=>setConnectorForm({...connectorForm,url:e.target.value})}/><input placeholder="Allowed tools (optional, comma separated)" value={connectorForm.allowed_tools} onChange={e=>setConnectorForm({...connectorForm,allowed_tools:e.target.value})}/><button className="auth-submit" onClick={addConnector} disabled={connectorLoading}>{connectorLoading?"Adding...":"Add connector"}</button></div><div className="connector-list">{connectors.length===0?<p>No connectors added.</p>:connectors.map(c=><div className="connector-item" key={c.id}><div><b>{c.name}</b><small>{c.transport} · {c.url}</small></div><button className="chat-more" onClick={()=>deleteConnectorById(c.id)}>Delete</button></div>)}</div></div></div>}
 </div>
}
createRoot(document.getElementById("root")).render(<App/>);