import React,{useRef} from "react";
import {Paperclip} from "lucide-react";

export default function FileUpload({onFile}){
 const ref=useRef(null);
 return <><input ref={ref} type="file" hidden onChange={e=>{const f=e.target.files?.[0];if(f)onFile(f);e.target.value=""}}/><button className="icon" type="button" onClick={()=>ref.current?.click()} title="Attach file"><Paperclip size={19}/></button></>;
}
