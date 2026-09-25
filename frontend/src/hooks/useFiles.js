import {useCallback,useState} from "react";

export default function useFiles({API,token,notify,setAttachments}){
 const [files,setFiles]=useState([]);
 const [uploading,setUploading]=useState(false);

 const loadFiles=useCallback(async()=>{
  if(!token)return;
  const r=await fetch(API+"/api/v1/files",{headers:{Authorization:"Bearer "+token}});
  if(r.ok)setFiles((await r.json()).files||[]);
 },[API,token]);

 async function uploadFile(file){
  setUploading(true);
  try{
   const fd=new FormData();fd.append("file",file);
   const r=await fetch(API+"/api/v1/files/upload",{method:"POST",headers:{Authorization:"Bearer "+token},body:fd});
   const d=await r.json();
   if(!r.ok){notify(d.detail||"Upload failed");return}
   setAttachments(a=>[...a,{path:d.path,name:d.name}]);
   await loadFiles();
   notify("File attached","success");
  }catch(e){notify("Upload failed")}
  finally{setUploading(false)}
 }

 function deleteFile(path){return {type:"file",path,message:"Delete this file? This also removes its indexed content."};}

 async function confirmDeleteFile(path){
  const r=await fetch(API+"/api/v1/files/"+path.split("/").map(encodeURIComponent).join("/"),{method:"DELETE",headers:{Authorization:"Bearer "+token}});
  if(r.ok)await loadFiles();else notify("Delete failed");
 }

 async function downloadFile(path){
  const r=await fetch(API+"/api/v1/files/"+path.split("/").map(encodeURIComponent).join("/"),{headers:{Authorization:"Bearer "+token}});
  if(!r.ok){notify("Download failed");return}
  const blob=await r.blob(),url=URL.createObjectURL(blob);
  window.location.href=url;
 }

 return {files,uploading,loadFiles,uploadFile,deleteFile,confirmDeleteFile,downloadFile};
}
