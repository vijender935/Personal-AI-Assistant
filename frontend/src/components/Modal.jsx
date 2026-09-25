import React from "react";

export default function Modal({title,onClose,children,className=""}){
 return <div className="overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose?.()}}>
  <div className={"settings "+className} role="dialog" aria-modal="true" aria-label={title}>
   <div className="settings-head"><h2>{title}</h2><button type="button" aria-label="Close" onClick={onClose}>×</button></div>
   {children}
  </div>
 </div>;
}
