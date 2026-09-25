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
  const next=[...chat.messages,{role:"user",content:message},{role:"assistant",content:""}];
  update(next); setText(""); setLoading(true);
  try{
   const r=await fetch(API+"/api/v1/chat/stream",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({message,session_id:"web-"+active,attachment_paths:attachments.map(a=>a.path)})});
   if(!r.ok){const d=await r.json();update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:d.detail||"Request failed."}]);return;}
   const reader=r.body.getReader(),decoder=new TextDecoder(); let buffer="",answer="";
   while(true){
    const {value,done}=await reader.read(); if(done)break;
    buffer+=decoder.decode(value,{stream:true});
    const events=buffer.split("\\n\\n"); buffer=events.pop()||"";
    for(const event of events){
     const line=event.split("\\n").find(x=>x.startsWith("data: "));
     if(!line)continue;
     try{
      const payload=JSON.parse(line.slice(6));
      if(payload.text){answer+=payload.text;update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:answer}]);}
     }catch(e){}
    }
   }
  }catch(e){
   update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:"Backend se connection nahi ho paaya. FastAPI server check karo."}]);
  }finally{setLoading(false);}
 };