import {useCallback,useState} from "react";

export const emptyForm={name:"",transport:"streamable-http",url:"",allowed_tools:"",headers:""};

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
     allowed_tools:connectorForm.allowed_tools.split(",").map(x=>x.trim()).filter(Boolean),
     headers:connectorForm.headers.trim()?JSON.parse(connectorForm.headers):{}
    })
   });
   const d=await r.json().catch(()=>({}));
   if(!r.ok){notify(d.detail||"Connector add failed");return}
   setConnectors(cs=>[...cs.filter(x=>x.id!==d.connector.id),d.connector]);
   setConnectorForm(emptyForm);
   if(d.status?.connected)notify(d.connector.name+" connected · "+(d.status.tools||0)+" tools","success");
   else notify(d.status?.error||"Connector saved but could not connect.");
  }catch(e){notify(e instanceof SyntaxError?"Headers must be valid JSON.":"Connector add failed")}
  finally{setConnectorLoading(false)}
 }

 async function testConnector(id){
  setConnectorTesting(id);
  try{
   const r=await fetch(API+"/api/v1/mcp/connectors/"+encodeURIComponent(id)+"/test",{method:"POST",headers:{Authorization:"Bearer "+token}});
   const d=await r.json().catch(()=>({}));
   if(!r.ok){notify(d.detail||"MCP test failed");return false}
   setConnectors(cs=>cs.map(c=>c.id===id?{...c,status:{connected:!!d.connected,tools:d.tools||0,tool_names:d.tool_names||[],error:d.error}}:c));
   if(d.connected){notify("MCP connected — "+(d.tools||0)+" tool(s) discovered","success");return true}
   notify(d.error||"MCP connection failed");return false;
  }catch{notify("MCP test failed");return false}finally{setConnectorTesting(null)}
 }

 async function deleteConnectorById(id){
  try{
   const r=await fetch(API+"/api/v1/mcp/connectors/"+encodeURIComponent(id),{method:"DELETE",headers:{Authorization:"Bearer "+token}});
   if(r.ok)setConnectors(cs=>cs.filter(x=>x.id!==id));else notify(await responseDetail(r,"Connector delete failed"));
  }catch{notify("Connector delete failed")}
 }

 async function startOAuth(id){
  try{
   const r=await fetch(API+"/api/v1/mcp/connectors/"+encodeURIComponent(id)+"/oauth/start",{method:"POST",headers:{Authorization:"Bearer "+token}});
   const d=await r.json().catch(()=>({}));
   if(!r.ok){notify(d.detail||"OAuth connection failed");return false}
   if(!d.authorization_url){notify("OAuth authorization URL was not returned");return false}
   window.open(d.authorization_url,"_blank","noopener,noreferrer");
   notify("Complete authorization in the browser…");
   for(let i=0;i<30;i++){
    await new Promise(resolve=>setTimeout(resolve,2000));
    const status=await fetch(API+"/api/v1/mcp/connectors/"+encodeURIComponent(id)+"/oauth/status",{headers:{Authorization:"Bearer "+token}});
    const sd=await status.json().catch(()=>({}));
    if(sd.connected){
     await testConnector(id);
     notify("MCP OAuth connected","success");
     return true;
    }
   }
   notify("Authorization is still pending. Test the connector after completing it.");
   return false;
  }catch{notify("OAuth connection failed");return false}
 }

 return {connectors,connectorForm,setConnectorForm,connectorLoading,connectorTesting,loadConnectors,addConnector,testConnector,startOAuth,deleteConnectorById};
}
