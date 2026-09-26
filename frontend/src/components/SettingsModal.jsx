import React,{useEffect,useState} from "react";
import {X,Palette,Smartphone,AppWindow,Globe2,SlidersHorizontal,Sparkles,Plug,BrainCircuit,Shield,Link2,Database,FileText,LockKeyhole,CircleHelp,LogOut,ChevronRight,ArrowLeft,Check,Info} from "lucide-react";

function Row({icon:Icon,title,subtitle,onClick,disabled=false}){
 return <button type="button" className="settings-row" onClick={onClick} disabled={disabled}>
  <span className="settings-row-icon"><Icon size={21} strokeWidth={1.9}/></span>
  <span className="settings-row-copy"><strong>{title}</strong>{subtitle&&<small>{subtitle}</small>}</span>
  <ChevronRight size={19} className="settings-chevron"/>
 </button>;
}
function Section({title,children}){return <section className="settings-section"><h3>{title}</h3><div className="settings-group">{children}</div></section>}

export default function SettingsModal({open,onClose,user,connectorForm,setConnectorForm,connectorLoading,connectorTesting,addConnector,testConnector,connectors,deleteConnectorById}){
 const [page,setPage]=useState("main");
 const [appearance,setAppearance]=useState("System");
 const [language,setLanguage]=useState("English");
 const [haptics,setHaptics]=useState(true);
 useEffect(()=>{if(open)setPage("main")},[open]);
 if(!open)return null;

 const name=user?.name?.trim()||user?.email?.split("@")[0]||"User";
 const initials=name.slice(0,1).toUpperCase();
 const canAdd=connectorForm.name.trim().length>0&&connectorForm.url.trim().length>0&&!connectorLoading;

 if(page==="connectors") return <div className="settings-screen">
  <div className="settings-page">
   <header className="settings-topbar">
    <button type="button" className="settings-icon-btn" aria-label="Back to settings" onClick={()=>setPage("main")}><ArrowLeft size={25}/></button>
    <h1>Connectors</h1><button type="button" className="settings-icon-btn" aria-label="Close settings" onClick={onClose}><X size={25}/></button>
   </header>
   <main className="settings-content">
    <Section title="MCP & Connectors">
     <div className="settings-inline-note"><Info size={18}/><span>Add a remote MCP server. Streamable HTTP and SSE are supported.</span></div>
     <div className="connector-form settings-connector-form">
      <input aria-label="Connector name" placeholder="Name (e.g. GitHub)" value={connectorForm.name} onChange={e=>setConnectorForm({...connectorForm,name:e.target.value})}/>
      <select aria-label="Connector transport" value={connectorForm.transport} onChange={e=>setConnectorForm({...connectorForm,transport:e.target.value})}><option value="streamable-http">Streamable HTTP</option><option value="sse">SSE</option></select>
      <input aria-label="MCP server URL" placeholder="MCP server URL" value={connectorForm.url} onChange={e=>setConnectorForm({...connectorForm,url:e.target.value})}/>
      <input aria-label="Allowed tools" placeholder="Allowed tools (optional, comma separated)" value={connectorForm.allowed_tools} onChange={e=>setConnectorForm({...connectorForm,allowed_tools:e.target.value})}/>
      <button type="button" className="settings-primary-btn" onClick={addConnector} disabled={!canAdd}>{connectorLoading?"Adding...":"Add connector"}</button>
     </div>
    </Section>
    <Section title="Your connectors">
     {connectors.length===0?<div className="settings-empty">No connectors added yet.</div>:connectors.map(c=><div className="connector-card" key={c.id}>
      <div className="connector-card-icon"><Plug size={19}/></div><div className="connector-card-copy"><strong>{c.name}</strong><small>{c.transport} · {c.url}</small></div>
      <div className="connector-actions"><button type="button" onClick={()=>testConnector(c.id)} disabled={connectorTesting===c.id}>{connectorTesting===c.id?"Testing…":"Test"}</button><button type="button" className="delete-link" onClick={()=>deleteConnectorById(c.id)}>Delete</button></div>
     </div>)}
    </Section>
   </main>
  </div>
 </div>;

 return <div className="settings-screen" role="dialog" aria-modal="true" aria-label="Settings">
  <div className="settings-page">
   <header className="settings-topbar">
    <button type="button" className="settings-icon-btn" aria-label="Close settings" onClick={onClose}><X size={29}/></button>
    <h1>Settings</h1><span className="settings-topbar-spacer"/>
   </header>
   <main className="settings-content">
    <button type="button" className="settings-profile">
     <span className="settings-avatar">{initials}</span><span><strong>{name.toUpperCase()}</strong><small>{user?.email||""}</small></span>
    </button>
    <div className="settings-account-card"><div className="settings-account-icon"><Sparkles size={22}/></div><div><strong>Personal AI</strong><small>Personal assistant · Groq model</small></div><span className="settings-status"><Check size={15}/> Active</span></div>

    <Section title="App">
     <Row icon={Palette} title="Appearance" subtitle={appearance} onClick={()=>setAppearance(appearance==="System"?"Light":appearance==="Light"?"Dark":"System")}/>
     <Row icon={Smartphone} title="Haptics" subtitle={haptics?"On":"Off"} onClick={()=>setHaptics(v=>!v)}/>
     <Row icon={AppWindow} title="Widget" subtitle="Coming soon" disabled/>
     <Row icon={Globe2} title="App Language" subtitle={language} onClick={()=>setLanguage(language==="English"?"Hindi":"English")}/>
     <Row icon={SlidersHorizontal} title="Advanced" subtitle="Connection, model and app options" onClick={()=>{}}/>
    </Section>

    <Section title="Personal AI">
     <Row icon={Sparkles} title="Customize Personal AI" subtitle="Instructions and response preferences" onClick={()=>{}}/>
     <Row icon={Plug} title="Connectors" subtitle={connectors.length?connectors.length+" connected":"Connect MCP servers"} onClick={()=>setPage("connectors")}/>
     <Row icon={BrainCircuit} title="Memory" subtitle="Manage saved memories" onClick={()=>{}}/>
     <Row icon={Shield} title="Privacy & Security" subtitle="Account and data settings" onClick={()=>{}}/>
    </Section>

    <Section title="Data & Information">
     <Row icon={Link2} title="Shared Conversations" subtitle="Manage shared links" onClick={()=>{}}/>
     <Row icon={Database} title="Data Controls" subtitle="Your chats and files" onClick={()=>{}}/>
     <Row icon={FileText} title="Open Source Licenses" onClick={()=>{}}/>
     <Row icon={LockKeyhole} title="Privacy Policy" onClick={()=>{}}/>
    </Section>

    <Section title="Support"><Row icon={CircleHelp} title="Report a Problem" onClick={()=>{}}/></Section>
    <button type="button" className="settings-signout" onClick={onClose}><LogOut size={20}/> Sign out</button>
    <footer className="settings-footer"><strong>Personal AI</strong><span>Version 1.0.0</span></footer>
   </main>
  </div>
 </div>;
}