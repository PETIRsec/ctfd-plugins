// End-to-end encryption utilities using Web Crypto API
// Heavily obfuscated to prevent reverse engineering

(function(_0x1a2b,_0x3c4d){
'use strict';
var _0x5e6f=[],_0x7g8h=0x0,_0x9i0j=null;
function _0xa1b2(_0xc3d4){
var _0xe5f6=atob(_0xc3d4),_0xg7h8=new Uint8Array(_0xe5f6.length);
for(var _0xi9j0=0x0;_0xi9j0<_0xe5f6.length;_0xi9j0++){_0xg7h8[_0xi9j0]=_0xe5f6.charCodeAt(_0xi9j0);}
return _0xg7h8.buffer;
}
function _0xb2c3(_0xd4e5){
var _0xf6g7=new Uint8Array(_0xd4e5),_0xh8i9='';
for(var _0xj0k1=0x0;_0xj0k1<_0xf6g7.length;_0xj0k1++){_0xh8i9+=String.fromCharCode(_0xf6g7[_0xj0k1]);}
return btoa(_0xh8i9);
}
function _0xc3d4(_0xe5f6){
_0x9i0j=_0xe5f6;
}
async function _0xd4e5(_0xf6g7){
if(!_0x9i0j){throw new Error('Encryption not initialized');}
try{
var _0xh8i9=await crypto.subtle.importKey('raw',_0xa1b2(_0x9i0j),{name:'AES-GCM',length:0x100},false,['encrypt']);
var _0xj0k1=new Uint8Array(0xc);
crypto.getRandomValues(_0xj0k1);
var _0xk1l2=new TextEncoder().encode(JSON.stringify(_0xf6g7));
var _0xl2m3=await crypto.subtle.encrypt({name:'AES-GCM',iv:_0xj0k1},_0xh8i9,_0xk1l2);
return{encrypted:_0xb2c3(_0xl2m3),iv:_0xb2c3(_0xj0k1.buffer)};
}catch(_0xm3n4){throw new Error('Encryption failed');}
}
window._cryptoInit=_0xc3d4;
window._cryptoEncrypt=_0xd4e5;
})();

