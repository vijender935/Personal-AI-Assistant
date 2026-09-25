import React,{useEffect} from "react";

export default function Modal({title,onClose,children,className=""}){
 useEffect(()=>{
  const onKeyDown=e=>{if(e.key==="Escape")onClose?.()};
  document.addEventListener("keydown",onKeyDown);
  return()=>document.removeEventListener("keydown",onKeyDown);
 },[onClose]);

 return <div className="overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose?.()}}>
  <div className={"settings "+className} role="dialog" aria-modal="true" aria-label={title}>
   <div className="settings-head"><h2>{title}</h2><button type="button" aria-label={"Close "+title} onClick={onClose}>×</button></div>
   {children}
  </div>
 </div>;
}
