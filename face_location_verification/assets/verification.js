document.addEventListener('DOMContentLoaded', function() {
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const captureBtn = document.getElementById('capture-btn');
    const captureLocationBtn = document.getElementById('capture-location-btn');
    const locationStatus = document.getElementById('location-status');
    const locationResult = document.getElementById('location-result');
    
    let stream = null;
    let capturedImage = null;
    
    // Initialize camera if face not already captured
    if (video && captureBtn) {
        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } })
            .then(function(mediaStream) {
                stream = mediaStream;
                video.srcObject = stream;
            })
            .catch(function(err) {
                console.error('Error accessing camera:', err);
                // Use textContent to prevent XSS
                const errorDiv = document.createElement('div');
                errorDiv.className = 'alert alert-danger';
                errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error accessing camera. Please ensure you have granted camera permissions.';
                locationStatus.innerHTML = '';
                locationStatus.appendChild(errorDiv);
            });
        
        captureBtn.addEventListener('click', function() {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            
            // Convert to base64
            capturedImage = canvas.toDataURL('image/jpeg', 0.8);
            
            // Stop the video stream
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
            
            // Encrypt data before sending (end-to-end encryption)
            const sendEncryptedData = async () => {
                try {
                    if (window._cryptoEncrypt && typeof window._cryptoEncrypt === 'function') {
                        // Encrypt the image data
                        const encrypted = await window._cryptoEncrypt({ image: capturedImage });
                        
                        // Send encrypted data to server
                        fetch('/face-location/capture-face', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'CSRF-Token': window.init ? window.init.csrfNonce : ''
                            },
                            body: JSON.stringify(encrypted)
                        })
                        .then(response => {
                            if (!response.ok) {
                                // If response is not OK, try to get error message
                                return response.text().then(text => {
                                    try {
                                        const json = JSON.parse(text);
                                        throw new Error(json.message || 'Request failed');
                                    } catch (e) {
                                        if (e instanceof Error && e.message !== 'Request failed') {
                                            throw e;
                                        }
                                        throw new Error('Request failed with status ' + response.status);
                                    }
                                });
                            }
                            return response.json();
                        })
                        .then(data => {
                            if (data.success) {
                                // Reload page to show success state
                                window.location.reload();
                            } else {
                                alert('Error: ' + data.message);
                            }
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            alert('Error capturing face: ' + error.message);
                        });
                    } else {
                        // Fallback: send unencrypted (should not happen in production)
                        console.warn('Encryption not available, sending unencrypted data');
                        fetch('/face-location/capture-face', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'CSRF-Token': window.init ? window.init.csrfNonce : ''
                            },
                            body: JSON.stringify({
                                image: capturedImage
                            })
                        })
                        .then(response => {
                            if (!response.ok) {
                                return response.text().then(text => {
                                    try {
                                        const json = JSON.parse(text);
                                        throw new Error(json.message || 'Request failed');
                                    } catch (e) {
                                        if (e instanceof Error && e.message !== 'Request failed') {
                                            throw e;
                                        }
                                        throw new Error('Request failed with status ' + response.status);
                                    }
                                });
                            }
                            return response.json();
                        })
                        .then(data => {
                            if (data.success) {
                                window.location.reload();
                            } else {
                                alert('Error: ' + data.message);
                            }
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            alert('Error capturing face: ' + error.message);
                        });
                    }
                } catch (error) {
                    console.error('Encryption error:', error);
                    alert('Error encrypting data: ' + error.message);
                }
            };
            
            sendEncryptedData();
        });
    }
    
    // Load captured face image if already captured
    const capturedFaceImg = document.getElementById('captured-face-img');
    if (capturedFaceImg) {
        // Get face image filename from data attribute set by template
        const faceImageFilename = capturedFaceImg.getAttribute('data-filename');
        if (faceImageFilename) {
            // Validate filename to prevent path traversal and XSS
            // Filename should only contain safe characters
            const safeFilename = faceImageFilename.replace(/[^a-zA-Z0-9_.-]/g, '');
            if (safeFilename === faceImageFilename && faceImageFilename.startsWith('face_') && faceImageFilename.endsWith('.jpg')) {
                // Use the filename in the route (server will validate again)
                capturedFaceImg.src = `/face-location/face-image/${encodeURIComponent(faceImageFilename)}`;
                capturedFaceImg.onerror = function() {
                    this.style.display = 'none';
                };
            } else {
                // Invalid filename, don't load image
                capturedFaceImg.style.display = 'none';
            }
        }
    }
    
    // Location capture
    if (captureLocationBtn) {
        captureLocationBtn.addEventListener('click', function() {
            if (!navigator.geolocation) {
                // Use textContent to prevent XSS
                const errorDiv = document.createElement('div');
                errorDiv.className = 'alert alert-danger';
                errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Geolocation is not supported by your browser.';
                locationStatus.innerHTML = '';
                locationStatus.appendChild(errorDiv);
                return;
            }
            
            // Use textContent to prevent XSS
            const infoDiv = document.createElement('div');
            infoDiv.className = 'alert alert-info';
            infoDiv.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Getting location...';
            locationStatus.innerHTML = '';
            locationStatus.appendChild(infoDiv);
            captureLocationBtn.disabled = true;
            
            navigator.geolocation.getCurrentPosition(
                function(position) {
                    const lat = position.coords.latitude;
                    const lng = position.coords.longitude;
                    
                    // Display location
                    document.getElementById('lat-display').textContent = lat.toFixed(6);
                    document.getElementById('lng-display').textContent = lng.toFixed(6);
                    locationResult.style.display = 'block';
                    
                    // Encrypt data before sending (end-to-end encryption)
                    const sendEncryptedLocation = async () => {
                        try {
                            if (window._cryptoEncrypt && typeof window._cryptoEncrypt === 'function') {
                                // Encrypt the location data
                                const encrypted = await window._cryptoEncrypt({ latitude: lat, longitude: lng });
                                
                                // Send encrypted data to server
                                fetch('/face-location/capture-location', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'CSRF-Token': window.init ? window.init.csrfNonce : ''
                                    },
                                    body: JSON.stringify(encrypted)
                                })
                                .then(response => {
                                    if (!response.ok) {
                                        // If response is not OK, try to get error message
                                        return response.text().then(text => {
                                            try {
                                                const json = JSON.parse(text);
                                                throw new Error(json.message || 'Request failed');
                                            } catch (e) {
                                                if (e instanceof Error && e.message !== 'Request failed') {
                                                    throw e;
                                                }
                                                throw new Error('Request failed with status ' + response.status);
                                            }
                                        });
                                    }
                                    return response.json();
                                })
                                .then(data => {
                                    if (data.success) {
                                        // Use textContent to prevent XSS
                                        const successDiv = document.createElement('div');
                                        successDiv.className = 'alert alert-success';
                                        successDiv.innerHTML = '<i class="fas fa-check-circle"></i> Location captured successfully!';
                                        locationStatus.innerHTML = '';
                                        locationStatus.appendChild(successDiv);
                                        if (data.verification_complete) {
                                            // Reload page to show completion
                                            setTimeout(() => {
                                                window.location.reload();
                                            }, 1000);
                                        }
                                    } else {
                                        // Escape user input to prevent XSS
                                        const errorDiv = document.createElement('div');
                                        errorDiv.className = 'alert alert-danger';
                                        const messageText = document.createTextNode(data.message || 'Unknown error');
                                        errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> ';
                                        errorDiv.appendChild(messageText);
                                        locationStatus.innerHTML = '';
                                        locationStatus.appendChild(errorDiv);
                                        captureLocationBtn.disabled = false;
                                    }
                                })
                                .catch(error => {
                                    console.error('Error:', error);
                                    // Escape error message to prevent XSS
                                    const errorDiv = document.createElement('div');
                                    errorDiv.className = 'alert alert-danger';
                                    const errorText = document.createTextNode('Error capturing location: ' + (error.message || 'Unknown error'));
                                    errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> ';
                                    errorDiv.appendChild(errorText);
                                    locationStatus.innerHTML = '';
                                    locationStatus.appendChild(errorDiv);
                                    captureLocationBtn.disabled = false;
                                });
                            } else {
                                // Fallback: send unencrypted (should not happen in production)
                                console.warn('Encryption not available, sending unencrypted data');
                                fetch('/face-location/capture-location', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'CSRF-Token': window.init ? window.init.csrfNonce : ''
                                    },
                                    body: JSON.stringify({
                                        latitude: lat,
                                        longitude: lng
                                    })
                                })
                                .then(response => {
                                    if (!response.ok) {
                                        return response.text().then(text => {
                                            try {
                                                const json = JSON.parse(text);
                                                throw new Error(json.message || 'Request failed');
                                            } catch (e) {
                                                if (e instanceof Error && e.message !== 'Request failed') {
                                                    throw e;
                                                }
                                                throw new Error('Request failed with status ' + response.status);
                                            }
                                        });
                                    }
                                    return response.json();
                                })
                                .then(data => {
                                    if (data.success) {
                                        const successDiv = document.createElement('div');
                                        successDiv.className = 'alert alert-success';
                                        successDiv.innerHTML = '<i class="fas fa-check-circle"></i> Location captured successfully!';
                                        locationStatus.innerHTML = '';
                                        locationStatus.appendChild(successDiv);
                                        if (data.verification_complete) {
                                            setTimeout(() => {
                                                window.location.reload();
                                            }, 1000);
                                        }
                                    } else {
                                        const errorDiv = document.createElement('div');
                                        errorDiv.className = 'alert alert-danger';
                                        const messageText = document.createTextNode(data.message || 'Unknown error');
                                        errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> ';
                                        errorDiv.appendChild(messageText);
                                        locationStatus.innerHTML = '';
                                        locationStatus.appendChild(errorDiv);
                                        captureLocationBtn.disabled = false;
                                    }
                                })
                                .catch(error => {
                                    console.error('Error:', error);
                                    const errorDiv = document.createElement('div');
                                    errorDiv.className = 'alert alert-danger';
                                    const errorText = document.createTextNode('Error capturing location: ' + (error.message || 'Unknown error'));
                                    errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> ';
                                    errorDiv.appendChild(errorText);
                                    locationStatus.innerHTML = '';
                                    locationStatus.appendChild(errorDiv);
                                    captureLocationBtn.disabled = false;
                                });
                            }
                        } catch (error) {
                            console.error('Encryption error:', error);
                            const errorDiv = document.createElement('div');
                            errorDiv.className = 'alert alert-danger';
                            const errorText = document.createTextNode('Error encrypting data: ' + error.message);
                            errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> ';
                            errorDiv.appendChild(errorText);
                            locationStatus.innerHTML = '';
                            locationStatus.appendChild(errorDiv);
                            captureLocationBtn.disabled = false;
                        }
                    };
                    
                    sendEncryptedLocation();
                },
                function(error) {
                    let errorMsg = 'Error getting location: ';
                    switch(error.code) {
                        case error.PERMISSION_DENIED:
                            errorMsg += 'Permission denied. Please allow location access.';
                            break;
                        case error.POSITION_UNAVAILABLE:
                            errorMsg += 'Position unavailable.';
                            break;
                        case error.TIMEOUT:
                            errorMsg += 'Request timeout.';
                            break;
                        default:
                            errorMsg += 'Unknown error.';
                            break;
                    }
                    // Use textContent to prevent XSS
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'alert alert-danger';
                    const errorText = document.createTextNode(errorMsg);
                    errorDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> ';
                    errorDiv.appendChild(errorText);
                    locationStatus.innerHTML = '';
                    locationStatus.appendChild(errorDiv);
                    captureLocationBtn.disabled = false;
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 0
                }
            );
        });
    }
    
    // Load captured location if already captured
    const capturedLat = document.getElementById('captured-lat');
    const capturedLng = document.getElementById('captured-lng');
    if (capturedLat && capturedLng) {
        // We'll need to pass this from the template
        // For now, this will be handled server-side
    }
});

