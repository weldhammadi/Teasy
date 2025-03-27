// Ajouter cette variable en haut du fichier pour éviter les soumissions multiples
let formSubmitting = false;

// Camera handling
let stream = null;

async function initCamera() {
    const video = document.getElementById('video');
    const cameraContainer = document.getElementById('cameraContainer');
    const toggleCameraBtn = document.getElementById('toggleCamera');
    const cameraError = document.getElementById('cameraError');

    // Hide any previous error messages
    cameraError.style.display = 'none';
    
    // Check if mediaDevices API is supported
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        console.error('Camera API not supported in this browser');
        cameraError.style.display = 'block';
        toggleCameraBtn.disabled = true;
        return;
    }

document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const uploadForm = document.getElementById('uploadForm');
    const preview = document.getElementById('preview');
    const imagePreview = document.getElementById('imagePreview');
    const loading = document.getElementById('loading');
    const selectFile = document.getElementById('selectFile');
    const toggleCamera = document.getElementById('toggleCamera');
    const captureButton = document.getElementById('captureButton');
    const canvas = document.getElementById('canvas');
    const video = document.getElementById('video');
    const cameraContainer = document.getElementById('cameraContainer');
    const directCameraInput = document.getElementById('directCameraInput');
    const uploadArea = document.getElementById('uploadArea');

    if (dropZone && fileInput) {
        // Handle drag and drop
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });

        // Handle file selection
        selectFile.addEventListener('click', () => {
            fileInput.click();
        });

        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });
        
        // Handle direct camera input for devices without MediaDevices API
        if (directCameraInput) {
            directCameraInput.addEventListener('change', (e) => {
                handleFiles(e.target.files);
            });
        }

        // Handle form submission - VERSION AMÉLIORÉE
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Vérifier si une soumission est déjà en cours
            if (formSubmitting) {
                console.log('Une soumission est déjà en cours, ignorée');
                return;
            }
            
            // Marquer comme en cours de soumission
            formSubmitting = true;
            
            if (!fileInput.files || fileInput.files.length === 0) {
                alert('Veuillez sélectionner un fichier ou prendre une photo d\'abord');
                formSubmitting = false;
                return;
            }

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            console.log('Fichier à télécharger:', fileInput.files[0].name, fileInput.files[0].size, 'octets');
            
            // Toujours utiliser la méthode de traitement combinée
            formData.append('processing_method', 'combined');

            // Masquer la zone de prévisualisation et afficher l'indicateur de chargement
            preview.style.display = 'none';
            uploadArea.style.display = 'none';
            loading.style.display = 'block';

            try {
                console.log('Envoi de la requête...');
                
                // Utiliser la fonction avec retentative au lieu d'un simple fetch
                const result = await uploadWithRetry(formData, 1); // Permettre 1 nouvelle tentative (2 au total)
                
                console.log('Réponse reçue:', result);

                if (result.success) {
                    console.log('Traitement réussi, navigation vers la page de détails du ticket');
                    window.location.href = '/receipt/' + result.receipt_id;
                } else {
                    console.error('Échec du traitement avec erreur:', result.error);
                    alert('Erreur: ' + (result.error || 'Échec du traitement du ticket'));
                    
                    // Réinitialiser l'interface pour une nouvelle tentative
                    loading.style.display = 'none';
                    uploadArea.style.display = 'block';
                    preview.style.display = 'block';
                }
            } catch (error) {
                console.error('Erreur finale de téléchargement:', error);
                alert('Erreur lors du téléchargement du fichier: ' + (error.message || 'Échec de connexion au serveur'));
                
                // Réinitialiser l'interface
                loading.style.display = 'none';
                uploadArea.style.display = 'block';
                preview.style.display = 'block';
            } finally {
                // Réinitialiser le statut de soumission pour permettre une nouvelle tentative
                formSubmitting = false;
                fileInput.value = ''; // Réinitialiser l'input du fichier
            }
        });
    }

    if (toggleCamera) {
        toggleCamera.addEventListener('click', async () => {
            if (!stream) {
                await initCamera();
            } else {
                stopCamera();
            }
        });
    }

    if (captureButton) {
        captureButton.addEventListener('click', () => {
            // Check if we're on iOS Safari
            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
            const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
            
            if (isIOS && isSafari) {
                // iOS Safari doesn't like the canvas approach, so we stop the video and take a frame
                video.pause();
                setTimeout(() => {
                    // Draw the paused video frame to canvas
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    canvas.getContext('2d').drawImage(video, 0, 0);
                    
                    canvas.toBlob((blob) => {
                        const file = new File([blob], "camera-capture.jpg", { type: "image/jpeg" });
                        handleFiles([file]);
                        stopCamera();
                    }, 'image/jpeg', 0.95);
                    
                    // Resume video in case they want to try again
                    video.play();
                }, 100);
            } else {
                // Normal approach for other browsers
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                canvas.getContext('2d').drawImage(video, 0, 0);
                canvas.toBlob((blob) => {
                    const file = new File([blob], "camera-capture.jpg", { type: "image/jpeg" });
                    handleFiles([file]);
                    stopCamera();
                }, 'image/jpeg', 0.95);
            }
        });
    }

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            if (file.type.startsWith('image/')) {
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                fileInput.files = dataTransfer.files;
                
                const reader = new FileReader();
                reader.onload = (e) => {
                    imagePreview.src = e.target.result;
                    preview.style.display = 'block';
                };
                reader.readAsDataURL(file);
            } else {
                alert('Veuillez télécharger une image');
            }
        }
    }
});

    try {
        toggleCameraBtn.textContent = 'Accessing camera...';
        toggleCameraBtn.disabled = true;
        
        // First try to get the environment camera (rear camera on phones)
        const constraints = {
            video: {
                facingMode: { ideal: "environment" }
            }
        };

        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch (backCameraError) {
            console.warn('Back camera failed, trying any camera:', backCameraError);
            // If that fails, try any camera
            stream = await navigator.mediaDevices.getUserMedia({ 
                video: true 
            });
        }

        // If we got a stream, set up the video
        if (stream) {
            video.srcObject = stream;
            video.onloadedmetadata = () => {
                video.play();
                cameraContainer.style.display = 'block';
                toggleCameraBtn.textContent = 'Close Camera';
                toggleCameraBtn.disabled = false;
            };
        }
    } catch (err) {
        console.error('Camera Error:', err);
        cameraError.style.display = 'block';
        toggleCameraBtn.textContent = 'Camera Not Available';
        toggleCameraBtn.disabled = true;
    }
}

function stopCamera() {
    const toggleCameraBtn = document.getElementById('toggleCamera');
    const video = document.getElementById('video');
    const cameraContainer = document.getElementById('cameraContainer');
    
    if (stream) {
        try {
            stream.getTracks().forEach(track => {
                track.stop();
            });
        } catch (e) {
            console.error('Error stopping camera tracks:', e);
        }
        stream = null;
    }
    
    if (video) {
        video.srcObject = null;
    }
    
    if (cameraContainer) {
        cameraContainer.style.display = 'none';
    }
    
    if (toggleCameraBtn) {
        toggleCameraBtn.textContent = 'Open Camera';
        toggleCameraBtn.disabled = false;
    }
}

// Function to upload with automatic retry - VERSION AMÉLIORÉE
async function uploadWithRetry(formData, maxRetries = 1) {
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            console.log(`Upload attempt ${attempt + 1}/${maxRetries + 1}`);
            
            // Ajouter un timeout plus long pour le traitement OCR
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 secondes
            
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData,
                signal: controller.signal
            });
            
            // Effacer le timeout
            clearTimeout(timeoutId);
            
            console.log('Response status:', response.status);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error(`HTTP error ${response.status}: ${errorText}`);
                throw new Error(`HTTP error ${response.status}: ${errorText}`);
            }
            
            // Analyser la réponse JSON
            const result = await response.json();
            console.log('Success response:', result);
            
            // Vérifier que la réponse contient les informations nécessaires
            if (!result || (result.success === false && !result.error)) {
                console.error('Invalid server response:', result);
                throw new Error('Invalid server response');
            }
            
            return result;
            
        } catch (error) {
            console.error(`Attempt ${attempt + 1} failed:`, error);
            
            // Si l'erreur est due à un timeout
            if (error.name === 'AbortError') {
                console.error('Request timed out');
            }
            
            if (attempt === maxRetries) {
                throw error; // Rethrow the error if we've reached max retries
            }
            
            // Wait before retrying with exponential backoff
            const waitTime = Math.min(2000 * Math.pow(2, attempt), 10000);
            console.log(`Waiting ${waitTime}ms before retry...`);
            await new Promise(resolve => setTimeout(resolve, waitTime));
        }
    }
}