// End-to-end encryption utilities using Web Crypto API
// This file will be obfuscated to prevent deobfuscation

(function() {
    'use strict';
    
    // Encryption key will be injected by server
    let _0x4a2b = null;
    let _0x7c3d = null;
    
    // Initialize encryption with server-provided key
    function _0x9e1f(keyBase64, ivBase64) {
        _0x4a2b = keyBase64;
        _0x7c3d = ivBase64;
    }
    
    // Convert base64 to ArrayBuffer
    function _0xa5b2(base64) {
        const _0x1c3d = atob(base64);
        const _0x2e4f = new Uint8Array(_0x1c3d.length);
        for (let _0x3f5a = 0; _0x3f5a < _0x1c3d.length; _0x3f5a++) {
            _0x2e4f[_0x3f5a] = _0x1c3d.charCodeAt(_0x3f5a);
        }
        return _0x2e4f.buffer;
    }
    
    // Convert ArrayBuffer to base64
    function _0xb6c3(buffer) {
        const _0x4d7e = new Uint8Array(buffer);
        let _0x5e8f = '';
        for (let _0x6f9a = 0; _0x6f9a < _0x4d7e.length; _0x6f9a++) {
            _0x5e8f += String.fromCharCode(_0x4d7e[_0x6f9a]);
        }
        return btoa(_0x5e8f);
    }
    
    // Encrypt data using AES-GCM
    async function _0xc7d4(data) {
        if (!_0x4a2b || !_0x7c3d) {
            throw new Error('Encryption not initialized');
        }
        
        try {
            const _0x8a1b = await crypto.subtle.importKey(
                'raw',
                _0xa5b2(_0x4a2b),
                { name: 'AES-GCM', length: 256 },
                false,
                ['encrypt']
            );
            
            const _0x9b2c = _0xa5b2(_0x7c3d);
            const _0xac3d = new TextEncoder().encode(JSON.stringify(data));
            
            const _0xbd4e = await crypto.subtle.encrypt(
                { name: 'AES-GCM', iv: _0x9b2c },
                _0x8a1b,
                _0xac3d
            );
            
            return {
                encrypted: _0xb6c3(_0xbd4e),
                iv: _0x7c3d
            };
        } catch (_0xce5f) {
            throw new Error('Encryption failed: ' + _0xce5f.message);
        }
    }
    
    // Export functions to global scope
    window._cryptoInit = _0x9e1f;
    window._cryptoEncrypt = _0xc7d4;
})();

