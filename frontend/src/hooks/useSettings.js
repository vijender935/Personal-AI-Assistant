import {apiFetch} from "../api";
import {useCallback,useState} from "react";
export const DEFAULT_SETTINGS={appearance:"System",haptics:true,language:"English",web_search:true,memory:true,custom_instructions:"",response_style:"Natural"};
export default function useSettings({API,notify}){
 const [settings,setSettings]=useState(DEFAULT_SETTINGS),[settingsLoading,setSettingsLoading]=useState(false);
 const loadSettings=useCallback(async()=>{try{const r=await apiFetch(API+"/api/v1/settings");const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||"Could not load settings");setSettings({...DEFAULT_SETTINGS,...d.settings})}catch(e){notify(e.message||"Could not load settings")}},[API,notify]);
 const updateSettings=useCallback(async(patch)=>{setSettingsLoading(true);try{const r=await apiFetch(API+"/api/v1/settings",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(patch)});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||"Could not save setting");setSettings({...DEFAULT_SETTINGS,...d.settings});return d.settings}catch(e){notify(e.message||"Could not save setting");return null}finally{setSettingsLoading(false)}},[API,notify]);
 return {settings,setSettings,settingsLoading,loadSettings,updateSettings};
}