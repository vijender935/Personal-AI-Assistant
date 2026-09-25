import {useCallback,useState} from "react";

async function responseDetail(response,fallback){
 try{const data=await response.json();return data.detail||fallback}catch{return fallback}
}

export default function useMemory({API,token,notify}){
 const [memories,setMemories]=useState([]);
 const [memoryForm,setMemoryForm]=useState("");

 const loadMemories=useCallback(async()=>{
  if(!token)return;
  try{
   const r=await fetch(API+"/api/v1/memories",{headers:{Authorization:"Bearer "+token}});
   if(!r.ok){notify("Could not load memories");return}
   setMemories((await r.json()).memories||[]);
  }catch{notify("Could not load memories")}
 },[API,token,notify]);

 async function saveMemory(){
  const fact=memoryForm.trim();
  if(!fact)return;
  try{
   const r=await fetch(API+"/api/v1/memories",{
    method:"POST",
    headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},
    body:JSON.stringify({fact,source:"settings"})
   });
   if(!r.ok){notify(await responseDetail(r,"Memory save failed"));return}
   setMemoryForm("");
   await loadMemories();
  }catch{notify("Memory save failed")}
 }

 async function deleteMemory(fact){
  try{
   const r=await fetch(API+"/api/v1/memories?fact="+encodeURIComponent(fact),{method:"DELETE",headers:{Authorization:"Bearer "+token}});
   if(r.ok)setMemories(ms=>ms.filter(x=>x!==fact));else notify(await responseDetail(r,"Memory delete failed"));
  }catch{notify("Memory delete failed")}
 }

 return {memories,memoryForm,setMemoryForm,loadMemories,saveMemory,deleteMemory};
}
