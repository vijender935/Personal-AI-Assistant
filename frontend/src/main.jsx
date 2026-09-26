import React,{useEffect,useState} from "react";
import {createRoot} from "react-dom/client";
import {Menu,User} from "lucide-react";
import useChat from "./hooks/useChat";
import useFiles from "./hooks/useFiles";
import useMemory from "./hooks/useMemory";
import useMCP from "./hooks/useMCP";
import ChatView from "./components/ChatView";
import Composer from "./components/Composer";
import Sidebar from "./components/Sidebar";
import FilesModal from "./components/FilesModal";
import MemoryModal from "./components/MemoryModal";
import SettingsModal from "./components/SettingsModal";
import "./styles.css";

const API=import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const initial=[{id:"new",title:"New conversation",messages:[]}];

function App(){
 const [chats,setChats]=useState(initial),[active,setActive]=useState("new"),[text,setText]=useState(""),[loading,setLoading]=useState(false),[sidebar,setSidebar]=useState(true),[settings,setSettings]=useState(false),[filesOpen,setFilesOpen]=useState(false),[fileQuery,setFileQuery]=useState(""),[user,setUser]=useState(null),[auth,setAuth]=useState({email:"",password:"",name:""}),[authMode,setAuthMode]=useState("login"),[authLoading,setAuthLoading]=useState(false),[attachments,setAttachments]=useState([]),[chatQuery,setChatQuery]=useState(""),[copiedMessage,setCopiedMessage]=useState(null),[memoryOpen,setMemoryOpen]=useState(false),[toast,setToast]=useState(null),[confirmState,setConfirmState]=useState(null),[editState,setEditState]=useState(null),[renameState,setRenameState]=useState(null),[webSearch,setWebSearch]=useState(true),[memory,setMemory]=useState(true);
 const token=localStorage.getItem("personal_ai_token");
 function notify(message,type="error"){setToast({message,type});window.clearTimeout(notify.timer);notify.timer=window.setTimeout(()=>setToast(null),3200)}
 function normalizeMessages(messages=[]){
  const result=[];
  for(const m of messages){
   if(result.length&&result.at(-1)?.role===m.role&&result.at(-1)?.content===m.content)continue;
   result.push(m);
  }
  return result;
 }

 useEffect(()=>{if(!token)return;fetch(API+"/api/v1/auth/me",{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(r.ok)setUser((await r.json()).user);else{localStorage.removeItem("personal_ai_token");setUser(null)}}).catch(()=>{});},[token]);
 useEffect(()=>{if(!token||!user)return;fetch(API+"/api/v1/chats",{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(!r.ok)return;const d=await r.json();if(d.chats?.length){const normalized=d.chats.map(c=>({...c,id:c.session_id,messages:normalizeMessages(c.messages)}));setChats(normalized);setActive(normalized[0].id)}}).catch(()=>{});},[token,user]);
 useEffect(()=>{if(!token||!user||!active||active==="new")return;let cancelled=false;fetch(API+"/api/v1/chats/"+encodeURIComponent(active),{headers:{Authorization:"Bearer "+token}}).then(async r=>{if(!r.ok)return;const d=await r.json();if(cancelled)return;setChats(cs=>cs.map(c=>c.id===active?{...c,messages:normalizeMessages(d.messages||[])}:c));}).catch(()=>{});return()=>{cancelled=true}},[active,token,user]);

 useEffect(()=>{if(user){loadFiles();loadConnectors();loadMemories()}},[user]);
 const {chat,update,regenerate,editLastUser,send,stopStream,newChat}=useChat({API,token,chats,setChats,active,setActive,text,setText,attachments,setAttachments,loading,setLoading,notify,webSearch,memory});
 const {files,uploading,loadFiles,uploadFile,deleteFile,confirmDeleteFile,downloadFile}=useFiles({API,token,notify,setAttachments,requestDelete:setConfirmState});
 const {memories,memoryForm,setMemoryForm,loadMemories,saveMemory,deleteMemory}=useMemory({API,token,notify});
 const {connectors,connectorForm,setConnectorForm,connectorLoading,connectorTesting,loadConnectors,addConnector,testConnector,deleteConnectorById}=useMCP({API,token,notify});




 async function logout(){try{if(token)await fetch(API+"/api/v1/auth/logout",{method:"POST",headers:{Authorization:"Bearer "+token}})}catch(e){}localStorage.removeItem("personal_ai_token");setUser(null);setChats(initial);setActive("new");}
 async function authSubmit(){
  if(authLoading)return;
  const email=auth.email.trim(),password=auth.password;
  if(!email||!password){notify("Email and password are required");return}
  setAuthLoading(true);
  try{
   const path=authMode==="login"?"/api/v1/auth/login":"/api/v1/auth/register";
   const body=authMode==="login"?{email,password}:auth;
   const r=await fetch(API+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
   const d=await r.json().catch(()=>({}));
   if(!r.ok){notify(d.detail||"Authentication failed");return}
   if(!d.token||!d.user){notify("Authentication failed: invalid server response");return}
   localStorage.setItem("personal_ai_token",d.token);
   setUser(d.user);
   setAuth({email:"",password:"",name:""});
  }catch{notify("Could not reach the server. Please try again.")}
  finally{setAuthLoading(false)}
 }
 function copyMessage(content,index){try{navigator.clipboard.writeText(content);setCopiedMessage(index);setTimeout(()=>setCopiedMessage(null),1500)}catch(e){}}
 async function renameChat(id,currentTitle){setRenameState({id,value:currentTitle});}
 async function submitRename(){
  const {id,value}=renameState||{};const title=value?.trim();
  if(!id||!title){notify("Chat name cannot be empty");return}
  if(title===chats.find(c=>c.id===id)?.title){setRenameState(null);return}
  const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(id),{method:"PATCH",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({title})});
  if(r.ok){setChats(cs=>cs.map(c=>c.id===id?{...c,title}:c));setRenameState(null)}else notify("Rename failed");
 }
 function deleteChatById(id){setConfirmState({type:"chat",id,message:"Delete this conversation?"});}
 async function confirmDeleteChat(id){
  const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(id),{method:"DELETE",headers:{Authorization:"Bearer "+token}});
  if(!r.ok){notify("Delete failed");return}
  const remaining=chats.filter(c=>c.id!==id);
  setChats(remaining.length?remaining:[{id:"new",title:"New conversation",messages:[]}]);
  if(active===id)setActive(remaining[0]?.id||"new");
 }
 if(!user&&!token)return <div className="auth-screen"><div className="auth-card"><div className="welcome-logo">✦</div><h1>{authMode==="login"?"Welcome back":"Create account"}</h1>{authMode==="register"&&<input placeholder="Name" value={auth.name} onChange={e=>setAuth({...auth,name:e.target.value})}/>}<input placeholder="Email" type="email" value={auth.email} onChange={e=>setAuth({...auth,email:e.target.value})}/><input placeholder="Password" type="password" value={auth.password} onChange={e=>setAuth({...auth,password:e.target.value})} onKeyDown={e=>{if(e.key==="Enter")authSubmit()}}/><button className="auth-submit" onClick={authSubmit} disabled={authLoading}>{authLoading?<><span className="auth-spinner"/>{authMode==="login"?"Signing in…":"Creating account…"}</>:authMode==="login"?"Sign in":"Sign up"}</button><button className="auth-switch" disabled={authLoading} onClick={()=>setAuthMode(authMode==="login"?"register":"login")}>{authMode==="login"?"Create an account":"Already have an account? Login"}</button></div></div>;

 return <div className="app">
  <Sidebar chats={chats} active={active} sidebar={sidebar} setSidebar={setSidebar} chatQuery={chatQuery} setChatQuery={setChatQuery} newChat={newChat} setActive={setActive} renameChat={renameChat} deleteChatById={deleteChatById} onFiles={()=>{setFilesOpen(true);loadFiles()}} onMemory={()=>{setMemoryOpen(true);loadMemories()}} onSettings={()=>setSettings(true)} logout={logout}/>
  <main className="main"><header>{!sidebar&&<button className="icon" onClick={()=>setSidebar(true)}><Menu size={20}/></button>}<div className="model">Personal AI <b>{user?.name||user?.email}</b></div><button className="avatar" onClick={()=>setSettings(true)}><User size={17}/></button></header>
   <ChatView chat={chat} loading={loading} copyMessage={copyMessage} copiedMessage={copiedMessage} regenerate={regenerate} editLastUser={editLastUser} setEditState={setEditState}/>
   <Composer text={text} setText={setText} loading={loading} send={send} stopStream={stopStream} uploadFile={uploadFile} attachments={attachments} setAttachments={setAttachments} uploading={uploading} webSearch={webSearch} setWebSearch={setWebSearch} memory={memory} setMemory={setMemory} onProject={()=>notify("Projects are not enabled yet","success")} onConnectors={()=>setSettings(true)}/>
  {toast&&<div className={"toast "+toast.type}>{toast.message}</div>}
  {confirmState&&<div className="overlay"><div className="confirm-card"><h3>Are you sure?</h3><p>{confirmState.message}</p><div className="modal-actions"><button className="secondary" onClick={()=>setConfirmState(null)}>Cancel</button><button className="danger" onClick={async()=>{const x=confirmState;if(x.type==="chat")await confirmDeleteChat(x.id);else await confirmDeleteFile(x.path);setConfirmState(null)}}>Delete</button></div></div></div>}
  {editState&&<div className="overlay"><div className="confirm-card"><div className="settings-head"><h3>Edit message</h3><button onClick={()=>setEditState(null)}>×</button></div><textarea className="modal-textarea" value={editState.value} onChange={e=>setEditState({...editState,value:e.target.value})}/><div className="modal-actions"><button className="secondary" onClick={()=>setEditState(null)}>Cancel</button><button className="primary" onClick={async()=>{const message=editState.value.trim();if(!message){notify("Message cannot be empty");return}const userIndex=editState.index;setEditState(null);setLoading(true);try{const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(active)+"/edit",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({message,session_id:active})});const d=await r.json();if(!r.ok){notify(d.detail||"Edit failed");return}update([...chat.messages.slice(0,userIndex),{role:"user",content:message},{role:"assistant",content:d.answer}])}finally{setLoading(false)}}}>Save & resend</button></div></div></div>}
  {renameState&&<div className="overlay"><div className="confirm-card"><div className="settings-head"><h3>Rename chat</h3><button onClick={()=>setRenameState(null)}>×</button></div><input className="modal-input" autoFocus value={renameState.value} onChange={e=>setRenameState({...renameState,value:e.target.value})} onKeyDown={e=>{if(e.key==="Enter")submitRename()}}/><div className="modal-actions"><button className="secondary" onClick={()=>setRenameState(null)}>Cancel</button><button className="primary" onClick={submitRename}>Rename</button></div></div></div>}
  </main>
  <FilesModal open={filesOpen} onClose={()=>setFilesOpen(false)} files={files} fileQuery={fileQuery} setFileQuery={setFileQuery} downloadFile={downloadFile} deleteFile={deleteFile}/>
  <MemoryModal open={memoryOpen} onClose={()=>setMemoryOpen(false)} memories={memories} memoryForm={memoryForm} setMemoryForm={setMemoryForm} saveMemory={saveMemory} deleteMemory={deleteMemory}/>
  <SettingsModal open={settings} onClose={()=>setSettings(false)} user={user} connectorForm={connectorForm} setConnectorForm={setConnectorForm} connectorLoading={connectorLoading} connectorTesting={connectorTesting} addConnector={addConnector} testConnector={testConnector} connectors={connectors} deleteConnectorById={deleteConnectorById}/>

 </div>
}
createRoot(document.getElementById("root")).render(<App/>);