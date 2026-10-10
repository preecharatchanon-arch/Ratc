'use strict';

// Optional browser persistence must never make the operational UI unavailable.
function storageRead(storageName,key,fallback=null){
  try{return globalThis[storageName].getItem(key)??fallback;}catch{return fallback;}
}
function storageWrite(storageName,key,value){
  try{globalThis[storageName].setItem(key,value);return true;}catch{return false;}
}
function storageRemove(storageName,key){
  try{globalThis[storageName].removeItem(key);return true;}catch{return false;}
}
function readNotificationIds(key){
  try{const ids=JSON.parse(storageRead('sessionStorage',key,'[]'));return new Set(Array.isArray(ids)?ids.filter(Number.isFinite).slice(-100):[]);}catch{return new Set();}
}

function requestErrorMessage(body,status){
  if(status===401)return 'Your session has expired or is not authorized. Reopen the app using the launch link from notebook cell 2.';
  if(status===403)return 'This action is not allowed for the current session. Check your access before retrying.';
  const detail=body?.detail??body;
  if(Array.isArray(detail)){
    const messages=detail.slice(0,5).map(item=>{
      if(typeof item==='string')return item;
      const field=Array.isArray(item?.loc)?item.loc.filter(part=>!['body','query','path'].includes(part)).join(' → '):'';
      const message=typeof item?.msg==='string'?item.msg:'Invalid value';
      return field?`${field}: ${message}`:message;
    });
    if(messages.length)return messages.join('; ')+(detail.length>5?'; review the remaining fields.':'');
  }
  if(typeof detail==='string'&&detail.trim()&&!/<(?:!doctype|html|body|head)\b/i.test(detail))return detail.trim().slice(0,600);
  if(typeof detail?.message==='string')return detail.message.slice(0,600);
  if(status>=500)return `The server could not complete this request (HTTP ${status}). Check the runtime connection and try again.`;
  return `Request could not be completed (HTTP ${status}). Review your input and try again.`;
}

function setDownloadLink(element,url){
  if(!element)return;
  const enabled=!!url;
  element.classList.toggle('disabled',!enabled);
  element.setAttribute('aria-disabled',String(!enabled));
  if(enabled){element.setAttribute('href',url);element.removeAttribute('tabindex');}
  else{element.removeAttribute('href');element.setAttribute('tabindex','-1');}
}
