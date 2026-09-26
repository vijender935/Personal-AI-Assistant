export async function apiFetch(input,init={}){return fetch(input,{...init,credentials:"include",headers:{"Accept":"application/json",...(init.headers||{})}})}
