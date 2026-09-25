import React from "react";
import {Files,Download,Trash2} from "lucide-react";
import Modal from "./Modal";

export default function FilesModal({open,onClose,files,fileQuery,setFileQuery,downloadFile,deleteFile}){
 if(!open)return null;
 const filtered=files.filter(f=>f.path.toLowerCase().includes(fileQuery.toLowerCase()));
 return <Modal title="Files" onClose={onClose}><input className="file-search" placeholder="Search files..." value={fileQuery} onChange={e=>setFileQuery(e.target.value)}/>{filtered.length===0?<p>No uploaded files.</p>:filtered.map(f=><div key={f.path} style={{display:"flex",alignItems:"center",gap:8,padding:"9px 0",borderBottom:"1px solid #eee"}}><Files size={16}/><span style={{flex:1,overflow:"hidden",textOverflow:"ellipsis"}}>{f.path}</span><small>{f.rag_indexed?"RAG ✓":"Not indexed"} · {Math.ceil(f.size/1024)} KB</small><button className="icon" onClick={()=>downloadFile(f.path)}><Download size={16}/></button><button className="icon" onClick={()=>deleteFile(f.path)}><Trash2 size={16}/></button></div>)}</Modal>;
}