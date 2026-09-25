import React,{useEffect,useRef} from "react";

export default function Modal({title,onClose,children,className=""}){
 const closeRef=useRef(null);
 useEffect(()=>{
  closeRef.current?.focus();
  const onKeyDown=e=>{if(e.key==="Escape")onClose?.()};
  document.addEventListener("keydown",onKeyDown);
  return()=>document.removeEventListener("keydown",onKeyDown);
 },[onClose]);

 return <div className="overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose?.()}}>
  <div className={"settings "+className} role="dialog" aria-modal="true" aria-labelledby="modal-title">
   <div className="settings-head"><h2 id="modal-title">{title}</h2><button ref={closeRef} type="button" aria-label={"Close "+title} onClick={onClose}>×</button></div>
   {children}
  </div>
 </div>;
}
