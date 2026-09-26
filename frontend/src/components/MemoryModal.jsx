import React from "react";
import Modal from "./Modal";

export default function MemoryModal({open,onClose,memories,memoryForm,setMemoryForm,saveMemory,deleteMemory}){
 if(!open)return null;
 return <Modal title="Memory" className="settings-large" onClose={onClose}><p>Your saved assistant memories.</p><div className="connector-form"><input placeholder="Remember something..." value={memoryForm} onChange={e=>setMemoryForm(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();saveMemory()}}}/><button className="settings-primary-btn" onClick={saveMemory}>Save memory</button></div><div className="connector-list">{memories.length===0?<p>No saved memories.</p>:memories.map((m,i)=><div className="connector-item" key={i}><div><span>{m}</span></div><button className="chat-more" onClick={()=>deleteMemory(m)}>Delete</button></div>)}</div></Modal>;
}