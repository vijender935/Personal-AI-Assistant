import React,{useEffect,useRef,useState} from "react";
import {Plus,Camera,Image as ImageIcon,FileUp} from "lucide-react";

export default function FileUpload({onFiles,disabled=false}){
 const [open,setOpen]=useState(false);
 const cameraRef=useRef(null),photoRef=useRef(null),fileRef=useRef(null);
 useEffect(()=>{
  if(!open)return;
  const close=()=>setOpen(false);
  document.addEventListener("click",close);
  return()=>document.removeEventListener("click",close);
 },[open]);
 const pick=(ref)=>{setOpen(false);ref.current?.click()};
 const handle=(e)=>{const files=[...(e.target.files||[])];if(files.length)onFiles(files);e.target.value=""};
 return <div className="add-menu-wrap" onClick={e=>e.stopPropagation()}>
  <button className={"icon add-button "+(open?"active":"")} type="button" disabled={disabled} onClick={()=>setOpen(x=>!x)} title="Add to chat"><Plus size={21}/></button>
  {open&&<div className="add-menu">
   <div className="add-menu-title">Add to chat</div>
   <div className="add-menu-grid">
    <button onClick={()=>pick(cameraRef)}><span><Camera size={22}/></span>Camera</button>
    <button onClick={()=>pick(photoRef)}><span><ImageIcon size={22}/></span>Photos</button>
    <button onClick={()=>pick(fileRef)}><span><FileUp size={22}/></span>Files</button>
   </div>
  </div>}
  <input ref={cameraRef} hidden type="file" accept="image/*" capture="environment" onChange={handle}/>
  <input ref={photoRef} hidden type="file" accept="image/*" multiple onChange={handle}/>
  <input ref={fileRef} hidden type="file" multiple onChange={handle}/>
 </div>;
}