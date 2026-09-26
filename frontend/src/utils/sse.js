export function parseSSEEvent(event,onEvent){
 const lines=event.split("\n");
 const type=lines.find(x=>x.startsWith("event:"))?.slice(6).trim()||"delta";
 const data=lines.filter(x=>x.startsWith("data:")).map(x=>x.slice(5).trimStart()).join("\n");
 if(data){
  try{onEvent(type,JSON.parse(data));}
  catch(error){throw new Error("Malformed streaming event.");}
 }
}
