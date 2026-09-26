import {useCallback,useEffect,useState} from "react";

export const DEFAULT_SETTINGS={
 appearance:"System",
 haptics:true,
 language:"English",
 web_search:true,
 memory:true,
 custom_instructions:"",
 response_style:"Natural"
};

export default function useSettings({API,token,notify}){
 const [settings,setSettings]=useState(DEFAULT_SETTINGS);
 const [settingsLoading,setSettingsLoading]=useState(false);

 const loadSettings=useCallback(async()=>{
  if(!token)return;
  try{
   const r=await fetch(API+"/api/v1/settings",{headers:{Authorization:"Bearer "+token}});
   const d=await r.json().catch(()=>({}));
   if(!r.ok)throw new Error(d.detail||"Could not load settings");
   setSettings({...DEFAULT_SETTINGS,...d.settings});
  }catch(e){notify(e.message||"Could not load settings")}
 },[API,token,notify]);

 useEffect(()=>{if(token)loadSettings()},[token,loadSettings]);

 const updateSettings=useCallback(async(patch)=>{
  setSettingsLoading(true);
  try{
   const r=await fetch(API+"/api/v1/settings",{
    method:"PATCH",
    headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},
    body:JSON.stringify(patch)
   });
   const d=await r.json().catch(()=>({}));
   if(!r.ok)throw new Error(d.detail||"Could not save setting");
   setSettings({...DEFAULT_SETTINGS,...d.settings});
   return d.settings;
  }catch(e){notify(e.message||"Could not save setting");return null}
  finally{setSettingsLoading(false)}
 },[API,token,notify]);

 return {settings,setSettings,settingsLoading,loadSettings,updateSettings};
}
