import {useState} from "react";

async function responseDetail(response,fallback){
 try{
  const data=await response.json();
  return data.detail||fallback;
 }catch{return fallback}
}

function parseSSEEvent(event,onEvent){
 const lines=event.split("\n");
 const type=lines.find(x=>x.startsWith("event:"))?.slice(6).trim()||"delta";
 const data=lines.filter(x=>x.startsWith("data:")).map(x=>x.slice(5).trimStart()).join("\n");
 if(data)onEvent(type,JSON.parse(data));
}

export default function useChat({API,token,chats,setChats,active,setActive,text,setText,attachments,setAttachments,loading,setLoading,notify}){
 const [streamController,setStreamController]=useState(null);
 const chat=chats.find(c=>c.id===active)||chats[0];

 function update(messages){
  setChats(cs=>cs.map(c=>c.id===active?{...c,messages,title:c.title==="New conversation"?(messages.find(m=>m.role==="user")?.content||"New conversation").slice(0,32):c.title}:c));
 }

 async function regenerate(){
  if(loading||!chat?.messages?.length)return;
  if(chat.messages.at(-1)?.role!=="assistant")return;
  setLoading(true);
  try{
   const r=await fetch(API+"/api/v1/chats/"+encodeURIComponent(active)+"/regenerate",{method:"POST",headers:{Authorization:"Bearer "+token}});
   if(!r.ok){notify(await responseDetail(r,"Regeneration failed"));return}
   const d=await r.json();
   update([...chat.messages.slice(0,-1),{role:"assistant",content:d.answer||""}]);
  }catch{notify("Regeneration failed")}
  finally{setLoading(false)}
 }

 function editLastUser(){
  if(loading||!chat?.messages?.length||chat.messages.length<2)return null;
  const userIndex=chat.messages.length-2,old=chat.messages[userIndex];
  return old.role==="user"?{value:old.content,index:userIndex}:null;
 }

 async function send(){
  const message=text.trim();
  if(!message||loading||!chat)return;
  const controller=new AbortController();
  setStreamController(controller);
  const next=[...chat.messages,{role:"user",content:message},{role:"assistant",content:""}];
  update(next);setText("");setLoading(true);
  try{
   const r=await fetch(API+"/api/v1/chat/stream",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({message,session_id:active,attachment_paths:attachments.map(a=>a.path)}),signal:controller.signal});
   if(!r.ok){update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:await responseDetail(r,"Request failed.")}]);return}
   if(!r.body)throw new Error("Streaming response unavailable.");
   const reader=r.body.getReader(),decoder=new TextDecoder();
   let buffer="",answer="";
   const handle=(type,p)=>{
    if(type==="error")throw new Error(p.detail||"Streaming failed.");
    if(p.text){answer+=p.text;update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:answer}]);}
   };
   while(true){
    const {value,done}=await reader.read();
    if(done)break;
    buffer+=decoder.decode(value,{stream:true});
    const events=buffer.split("\n\n");
    buffer=events.pop()||"";
    for(const event of events)if(event.trim())parseSSEEvent(event,handle);
   }
   buffer+=decoder.decode();
   if(buffer.trim())parseSSEEvent(buffer,handle);
   if(!answer)update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:"No response received."}]);
  }catch(e){
   if(e.name!=="AbortError")update([...next.slice(0,-1),{role:"user",content:message},{role:"assistant",content:e.message||"Streaming failed."}]);
  }finally{setLoading(false);setStreamController(null);setAttachments([])}
 }

 function stopStream(){streamController?.abort();setStreamController(null);setLoading(false)}
 function newChat(){
  const id="web-"+Date.now();
  setChats(cs=>[{id,title:"New conversation",messages:[]},...cs]);setActive(id);setAttachments([]);
  if(window.innerWidth<701)window.dispatchEvent(new Event("chat:new"));
 }
 return {chat,update,regenerate,editLastUser,send,stopStream,newChat};
}
