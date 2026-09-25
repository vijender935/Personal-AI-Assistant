import {useCallback,useState} from "react";

const emptyForm={name:"",transport:"streamable-http",url:"",allowed_tools:""};

export default function useMCP({API,token,notify}){
 const [connectors,setConnectors]=useState([]);
 const [connectorForm,setConnectorForm]=useState(emptyForm);
 const [connectorLoading,setConnectorLoading]=useState(false);

 const loadConnectors=useCallback(async()=>{
  if(!token)return;
  const r=await fetch(API+"/api/v1/mcp/connectors",{headers:{Authorization:"Bearer "+token}});
  if(r.ok)setConnectors((await r.json()).connectors||[]);
 },[API,token]);

 async function addConnector(){
  if(connectorLoading)return;
  setConnectorLoading(true);
  try{
   const r=await fetch(API+"/api/v1/mcp/connectors",{
    method:"POST",
    headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},
    body:JSON.stringify({
     name:connectorForm.name.trim(),
     transport:connectorForm.transport,
     url:connectorForm.url.trim(),
     allowed_tools:connectorForm.allowed_tools.split(",").map(x=>x.trim()).filter(Boolean)
    })
   });
   const d=await r.json();
   if(!r.ok){notify(d.detail||"Connector add failed");return}
   setConnectors(cs=>[...cs.filter(x=>x.id!==d.connector.id),d.connector]);
   setConnectorForm(emptyForm);
  }finally{setConnectorLoading(false)}
 }

 async function deleteConnectorById(id){
  const r=await fetch(API+"/api/v1/mcp/connectors/"+id,{method:"DELETE",headers:{Authorization:"Bearer "+token}});
  if(r.ok)setConnectors(cs=>cs.filter(x=>x.id!==id));else notify("Connector delete failed");
 }

 return {connectors,connectorForm,setConnectorForm,connectorLoading,loadConnectors,addConnector,deleteConnectorById};
}
