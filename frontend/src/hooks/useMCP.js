import {useCallback,useState} from "react";

export const emptyForm={name:"",transport:"streamable-http",url:"",allowed_tools:""};

async function responseDetail(response,fallback){
 try{const data=await response.json();return data.detail||fallback}catch{return fallback}
}

export default function useMCP({API,token,notify}){
 const [connectors,setConnectors]=useState([]);
 const [connectorForm,setConnectorForm]=useState(emptyForm);
 const [connectorLoading,setConnectorLoading]=useState(false);
 const [connectorTesting,setConnectorTesting]=useState(null);

 const loadConnectors=useCallback(async()=>{
  if(!token)return;
  try{
   const r=await fetch(API+"/api/v1/mcp/connectors",{headers:{Authorization:"Bearer "+token}});
   if(!r.ok){notify("Could not load connectors");return}
   setConnectors((await r.json()).connectors||[]);
  }catch{notify("Could not load connectors")}
 },[API,token,notify]);

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
   const d=await r.json().catch(()=>({}));
   if(!r.ok){notify(d.detail||"Connector add failed");return}
   setConnectors(cs=>[...cs.filter(x=>x.id!==d.connector.id),d.connector]);
   setConnectorForm(emptyForm);
  }catch{notify("Connector add failed")}
  finally{setConnectorLoading(false)}
 }

 async function testConnector(id){
  setConnectorTesting(id);
  try{
   const r=await fetch(API+"/api/v1/mcp/connectors/"+encodeURIComponent(id)+"/test",{method:"POST",headers:{Authorization:"Bearer "+token}});
   const d=await r.json().catch(()=>({}));
   if(!r.ok){notify(d.detail||"MCP test failed");return false}
   notify("MCP connected — "+d.tools+" tool(s) discovered","success");return true;
  }catch{notify("MCP test failed");return false}finally{setConnectorTesting(null)}
 }

 async function deleteConnectorById(id){
  try{
   const r=await fetch(API+"/api/v1/mcp/connectors/"+encodeURIComponent(id),{method:"DELETE",headers:{Authorization:"Bearer "+token}});
   if(r.ok)setConnectors(cs=>cs.filter(x=>x.id!==id));else notify(await responseDetail(r,"Connector delete failed"));
  }catch{notify("Connector delete failed")}
 }

 return {connectors,connectorForm,setConnectorForm,connectorLoading,connectorTesting,loadConnectors,addConnector,testConnector,deleteConnectorById};
}
