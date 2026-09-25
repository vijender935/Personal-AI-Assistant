import {useCallback,useState} from "react";

export default function useMemory({API,token,notify}){
 const [memories,setMemories]=useState([]);
 const [memoryForm,setMemoryForm]=useState("");

 const loadMemories=useCallback(async()=>{
  if(!token)return;
  const r=await fetch(API+"/api/v1/memories",{headers:{Authorization:"Bearer "+token}});
  if(r.ok)setMemories((await r.json()).memories||[]);
 },[API,token]);

 async function saveMemory(){
  const fact=memoryForm.trim();
  if(!fact)return;
  const r=await fetch(API+"/api/v1/memories",{
   method:"POST",
   headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},
   body:JSON.stringify({fact,source:"settings"})
  });
  if(!r.ok){const d=await r.json();notify(d.detail||"Memory save failed");return}
  setMemoryForm("");
  await loadMemories();
 }

 async function deleteMemory(fact){
  const r=await fetch(API+"/api/v1/memories?fact="+encodeURIComponent(fact),{method:"DELETE",headers:{Authorization:"Bearer "+token}});
  if(r.ok)setMemories(ms=>ms.filter(x=>x!==fact));else notify("Memory delete failed");
 }

 return {memories,memoryForm,setMemoryForm,loadMemories,saveMemory,deleteMemory};
}
