import {apiFetch} from "../api";
import {useCallback,useState} from "react";
export function fileUrl(API,path){return API+"/api/v1/files/"+path.split("/").map(encodeURIComponent).join("/")}
async function responseDetail(response,fallback){try{const data=await response.json();return data.detail||fallback}catch{return fallback}}
export default function useFiles({API,notify,setAttachments,requestDelete}){
 const [files,setFiles]=useState([]),[uploading,setUploading]=useState(false);
 const loadFiles=useCallback(async()=>{try{const r=await apiFetch(API+"/api/v1/files");if(!r.ok){notify(await responseDetail(r,"Could not load files"));return}setFiles((await r.json()).files||[])}catch{notify("Could not load files")}},[API,notify]);
 async function uploadFile(fileOrFiles){const selected=Array.isArray(fileOrFiles)?fileOrFiles:[fileOrFiles];if(!selected.length||uploading)return;setUploading(true);try{for(const file of selected){if(!file)continue;const fd=new FormData();fd.append("file",file);const r=await apiFetch(API+"/api/v1/files/upload",{method:"POST",body:fd});const d=await r.json().catch(()=>({}));if(!r.ok){notify(d.detail||"Upload failed");continue}if(d.path&&d.name)setAttachments(a=>[...a,{path:d.path,name:d.name}])}await loadFiles();notify("File(s) attached","success")}catch{notify("Upload failed")}finally{setUploading(false)}}
 function deleteFile(path){const confirmation={type:"file",path,message:"Delete this file? This also removes its indexed content."};requestDelete?.(confirmation);return confirmation}
 async function confirmDeleteFile(path){try{const r=await apiFetch(fileUrl(API,path),{method:"DELETE"});if(!r.ok){notify(await responseDetail(r,"Delete failed"));return}setFiles(fs=>fs.filter(f=>(f.path||f.name)!==path));setAttachments(a=>a.filter(f=>f.path!==path))}catch{notify("Delete failed")}}
 async function downloadFile(path){try{const r=await apiFetch(fileUrl(API,path));if(!r.ok){notify(await responseDetail(r,"Download failed"));return}const blob=await r.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=path.split("/").pop()||"download";document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),0)}catch{notify("Download failed")}}
 return {files,uploading,loadFiles,uploadFile,deleteFile,confirmDeleteFile,downloadFile};
}