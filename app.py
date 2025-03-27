from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, session, flash
from werkzeug.utils import secure_filename
import os
import socket
import uuid
import json
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from receipt_utils import ReceiptProcessor
from advanced_receipt_ocr import SimplifiedReceiptProcessor
from dotenv import load_dotenv
from db_integrator import DatabaseIntegrator
from gcp_storage import GCPStorageManager
from firestore_db import FirestoreManager
import logging
import sys

# Load environment variables
load_dotenv()

app = Flask(__name__)
# Ajout d'une clé secrète pour les sessions
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key_for_development")
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['DATA_DIR'] = Path(__file__).parent / 'data'
app.config['DB_PATH'] = Path(__file__).parent / 'fidelity_db.sqlite'
# Configurer le délai d'expiration de session à 1 heure
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

# GCP Storage configuration
app.config['GCP_BUCKET_NAME'] = os.getenv("GCP_BUCKET_NAME", "teasy_bucket")
app.config['GCP_CREDENTIALS_PATH'] = os.getenv("GCP_CREDENTIALS_PATH", os.path.join(os.path.dirname(__file__), "hackathon-ocr-2025-dbp-client.json"))
# Disable local fallback
app.config['USE_LOCAL_FALLBACK'] = False

#----------------------------------------------------------DEBOGAGE ------------------------------------------------

import traceback
import sys

# Redéfinir sys.excepthook pour capturer les traces détaillées des erreurs
def custom_excepthook(exc_type, exc_value, exc_traceback):
    # Format the exception traceback
    traceback_details = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    # Log the exception with traceback
    print("\n\n========= EXCEPTION DÉTAILLÉE =========")
    print(traceback_details)
    print("=======================================\n")
    
    # Log to file
    with open('error_trace.log', 'a') as f:
        f.write("\n\n========= NOUVELLE EXCEPTION =========\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(traceback_details)
        f.write("\n=======================================\n")
    
    # Also log to application logger if available
    try:
        app.logger.error(f"EXCEPTION: {exc_value}")
        app.logger.error(traceback_details)
    except Exception:
        pass
    
    # Call the original excepthook
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# Installer le custom excepthook
sys.excepthook = custom_excepthook

# Fonction pour configurer la journalisation améliorée
def setup_enhanced_logging():
    """Configure un système de journalisation amélioré pour le débogage"""
    from logging.handlers import RotatingFileHandler
    import os
    import sys
    import logging
    
    # Créer le dossier de logs s'il n'existe pas
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Clear all existing handlers from root logger and Flask logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    app.logger.handlers.clear()
    
    # Configure root logger
    root_logger.setLevel(logging.INFO)
    
    # Handler pour le fichier de log
    log_file = os.path.join(log_dir, 'receipt_app.log')
    file_handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=5)  # 10MB par fichier, 5 fichiers max
    file_handler.setLevel(logging.INFO)
    
    # Handler pour la console - only added to root logger
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Formateur pour les logs
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Configure Flask logger to propagate to root logger
    app.logger.propagate = True
    
    print("==== SYSTÈME DE JOURNALISATION CONFIGURÉ ====")
    logging.info("Système de journalisation amélioré configuré")

# Appel de la fonction de configuration de journalisation
setup_enhanced_logging()

# Initialize processors
veryfi_processor = ReceiptProcessor()
mistral_processor = SimplifiedReceiptProcessor()
db_integrator = DatabaseIntegrator(str(app.config['DB_PATH']))

# Check if credentials file exists
creds_path = app.config['GCP_CREDENTIALS_PATH']
if not os.path.exists(creds_path):
    app.logger.error(f"GCP credentials file not found at {creds_path}. The application will fail to start.")
    raise FileNotFoundError(f"GCP credentials file not found at {creds_path}")
else:
    app.logger.info(f"GCP credentials file found at {creds_path}")
    
# Print the service account information for debugging
try:
    with open(creds_path, 'r') as f:
        creds_data = json.load(f)
        app.logger.info(f"Service account: {creds_data.get('client_email')}")
        app.logger.info(f"Project ID: {creds_data.get('project_id')}")
except Exception as e:
    app.logger.error(f"Error reading credentials file: {str(e)}")

# Initialize GCP Storage Manager with timeout protection
try:
    app.logger.info(f"Initializing GCP Storage with bucket: {app.config['GCP_BUCKET_NAME']}")
    
    # Create a function to initialize storage with timeout
    def initialize_storage_with_timeout():
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        
        def init_storage():
            # Create the storage manager
            storage_mgr = GCPStorageManager(
                bucket_name=app.config['GCP_BUCKET_NAME'],
                credentials_path=creds_path,
                use_local_fallback=False
            )
            
            # Test the connection without listing blobs
            # Just check if the bucket exists, which is faster
            bucket = storage_mgr.bucket
            bucket_exists = bucket.exists()
            app.logger.info(f"Bucket exists: {bucket_exists}")
            return storage_mgr
            
        # Use ThreadPoolExecutor for timeout
        with ThreadPoolExecutor() as executor:
            future = executor.submit(init_storage)
            try:
                return future.result(timeout=10)  # 10 second timeout
            except TimeoutError:
                app.logger.error("GCP Storage initialization timed out after 10 seconds")
                raise TimeoutError("GCP Storage initialization timed out")
                
    # Initialize with timeout
    storage_manager = initialize_storage_with_timeout()
    app.logger.info("GCP Storage successfully initialized")
    
except Exception as e:
    app.logger.error(f"GCP Storage initialization error: {str(e)}")
    app.logger.error(f"Falling back to limited functionality mode")
    
    # Create a minimal storage manager with limited functionality
    from collections import namedtuple
    MockBlob = namedtuple('MockBlob', ['name'])
    
    class MockStorageManager:
        def __init__(self):
            self.bucket_name = "mock_bucket"
            
        def get_storage_status(self):
            return {"mode": "mock", "error": str(e), "bucket": None}
            
        def list_receipts(self, limit=100):
            return []
            
        def get_receipt_data(self, receipt_id):
            return None
            
        def upload_file(self, filepath, blob_name):
            return f"/static/placeholder.jpg"
            
        def upload_from_string(self, content, blob_name, content_type):
            return True
            
        def blob_exists(self, blob_name):
            return False
            
        @property
        def bucket(self):
            class MockBucket:
                def list_blobs(self, max_results=1):
                    return []
                    
                def blob(self, name):
                    return MockBlob(name=name)
            return MockBucket()
    
    storage_manager = MockStorageManager()
    app.logger.warning("Using mock storage manager due to initialization failure")

# Check storage status
storage_status = storage_manager.get_storage_status()
app.logger.info(f"Storage configuration: {storage_status}")

# Skip initializing Firestore for now
try:
    # Initialize Firestore NoSQL database
    # firestore_db = FirestoreManager(creds_path)
    # app.logger.info("Firestore NoSQL database initialized")
    app.logger.warning("Firestore initialization skipped, using GCP Storage only")
except Exception as e:
    app.logger.error(f"Failed to initialize Firestore: {str(e)}")

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DATA_DIR'] / 'csv', exist_ok=True)
os.makedirs(app.config['DATA_DIR'] / 'images', exist_ok=True)
os.makedirs(app.config['DATA_DIR'] / 'json', exist_ok=True)

# Add Jinja filter to parse JSON
@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {}

# Add route to show storage status
@app.route('/storage-status')
def storage_status():
    """Display current storage configuration"""
    status = storage_manager.get_storage_status()
    
    # Count items in storage
    receipt_count = len(storage_manager.list_receipts(limit=1000))
    
    status_data = {
        "status": status,
        "receipt_count": receipt_count,
        "app_config": {
            "GCP_BUCKET_NAME": app.config['GCP_BUCKET_NAME'],
            "GCP_CREDENTIALS_PATH": app.config['GCP_CREDENTIALS_PATH'],
            "USE_LOCAL_FALLBACK": app.config['USE_LOCAL_FALLBACK'],
        },
    }
    
    return render_template('storage_status.html', 
                          status=status_data,
                          title="Storage Configuration")

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        client_id = request.form.get('client_id')
        
        if not client_id:
            return render_template('login.html', error="Veuillez entrer un numéro client")
        
        try:
            # Tenter de récupérer les infos du client depuis la base de données
            if db_integrator.connect():
                db_integrator.cursor.execute(
                    "SELECT client_id, nom, prenom FROM clients WHERE client_id = ?", 
                    (client_id,)
                )
                client = db_integrator.cursor.fetchone()
                db_integrator.disconnect()
                
                if client:
                    # Stocker les infos du client en session
                    session.permanent = True
                    session['logged_in'] = True
                    session['client_id'] = client['client_id']
                    session['client_name'] = f"{client['prenom']} {client['nom']}"
                    
                    flash("Connexion réussie", "success")
                    return redirect(url_for('profile'))
                else:
                    return render_template('login.html', error="Client non trouvé")
            else:
                return render_template('login.html', error="Erreur de connexion à la base de données")
        
        except Exception as e:
            app.logger.error(f"Erreur de connexion: {str(e)}")
            return render_template('login.html', error=f"Erreur: {str(e)}")
    
    return render_template('login.html')

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash("Vous avez été déconnecté", "info")
    return redirect(url_for('index'))

# Profile route
@app.route('/profile')
def profile():
    if not session.get('logged_in'):
        flash("Veuillez vous connecter pour accéder à votre profil", "warning")
        return redirect(url_for('login'))
    
    client_id = session.get('client_id')
    client_info = {}
    transactions = []
    points_history = []
    
    try:
        if db_integrator.connect():
            # Récupérer les infos du client et de sa carte
            db_integrator.cursor.execute("""
                SELECT c.*, cf.numero_carte, cf.niveau_fidelite, cf.points_actuels, cf.date_expiration
                FROM clients c
                LEFT JOIN cartes_fidelite cf ON c.client_id = cf.client_id
                WHERE c.client_id = ?
            """, (client_id,))
            client_info = dict(db_integrator.cursor.fetchone() or {})
            
            # Récupérer les transactions récentes
            db_integrator.cursor.execute("""
                SELECT t.transaction_id, t.date_transaction, t.montant_total, 
                       t.points_gagnes, pv.nom as magasin_nom
                FROM transactions t
                LEFT JOIN points_vente pv ON t.magasin_id = pv.magasin_id
                WHERE t.client_id = ?
                ORDER BY t.date_transaction DESC
                LIMIT 5
            """, (client_id,))
            transactions = [dict(row) for row in db_integrator.cursor.fetchall()]
            
            # Récupérer l'historique des points
            db_integrator.cursor.execute("""
                SELECT date_operation, type_operation, points, description, solde_apres
                FROM historique_points
                WHERE client_id = ?
                ORDER BY date_operation DESC
                LIMIT 10
            """, (client_id,))
            points_history = [dict(row) for row in db_integrator.cursor.fetchall()]
            
            db_integrator.disconnect()
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération du profil: {str(e)}")
        flash(f"Erreur lors de la récupération de votre profil: {str(e)}", "danger")
    
    return render_template('profile.html', 
                          client=client_info, 
                          transactions=transactions,
                          points_history=points_history)

# My receipts route
@app.route('/my-receipts')
def my_receipts():
    if not session.get('logged_in'):
        flash("Veuillez vous connecter pour accéder à vos tickets", "warning")
        return redirect(url_for('login'))
        
    client_id = session.get('client_id')
    transactions = []
    
    try:
        if db_integrator.connect():
            # Récupérer toutes les transactions du client
            db_integrator.cursor.execute("""
                SELECT t.transaction_id, t.date_transaction, t.montant_total, 
                       t.points_gagnes, t.points_utilises, pv.nom as magasin_nom
                FROM transactions t
                LEFT JOIN points_vente pv ON t.magasin_id = pv.magasin_id
                WHERE t.client_id = ?
                ORDER BY t.date_transaction DESC
            """, (client_id,))
            transactions = [dict(row) for row in db_integrator.cursor.fetchall()]
            
            db_integrator.disconnect()
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des tickets: {str(e)}")
        flash(f"Erreur lors de la récupération de vos tickets: {str(e)}", "danger")
    
    return render_template('my_receipts.html', transactions=transactions, logged_in=True)

@app.route('/')
def index():
    # Add storage status info to the index page
    app.logger.info("Index page accessed")
    storage_info = storage_manager.get_storage_status()
    return render_template('index.html', storage_info=storage_info)

@app.route('/upload', methods=['POST'])
def upload_file():
    # Check if user is logged in
    if not session.get('logged_in'):
        app.logger.warning("Unauthenticated upload attempt")
        return jsonify({'success': False, 'error': 'Veuillez vous connecter pour scanner un ticket'}), 401
        
    # Logs de débogage améliorés
    app.logger.info("=== NOUVELLE REQUÊTE D'UPLOAD REÇUE ===")
    app.logger.info(f"Méthode: {request.method}")
    app.logger.info(f"Type de contenu: {request.content_type}")
    app.logger.info(f"Taille du contenu: {request.content_length} octets")
    app.logger.info(f"Headers: {dict(request.headers)}")
    app.logger.info(f"Fichiers: {list(request.files.keys()) if request.files else 'Aucun'}")
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Aucune partie de fichier'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Aucun fichier sélectionné'}), 400

    if file:
        # Generate a unique filename to prevent collisions
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = secure_filename(file.filename)
        filename = f"{timestamp}_{unique_id}_{safe_filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            # Ensure directory exists
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            # Save file with a timeout
            file.save(filepath)
            app.logger.info(f"Fichier sauvegardé localement: {filepath}")
            
            # Process with timeouts to prevent hanging
            from concurrent.futures import ThreadPoolExecutor, TimeoutError
            
            app.logger.info(f"Début du traitement du ticket: {filename}")
            
            # Define processing functions with timeouts
            def process_with_veryfi():
                try:
                    return veryfi_processor.process_image(filepath)
                except Exception as e:
                    app.logger.error(f"Erreur Veryfi: {str(e)}")
                    return {"ocr_text": "", "error": str(e)}
            
            def extract_with_tesseract():
                try:
                    return mistral_processor.extract_text(filepath)
                except Exception as e:
                    app.logger.error(f"Erreur Tesseract: {str(e)}")
                    return ""
                    
            def clean_with_mistral(text):
                try:
                    return mistral_processor.clean_text_with_mistral(text)
                except Exception as e:
                    app.logger.error(f"Erreur nettoyage Mistral: {str(e)}")
                    return text
                    
            def classify_with_mistral(text):
                try:
                    return mistral_processor.classify_data_with_mistral(text)
                except Exception as e:
                    app.logger.error(f"Erreur classification Mistral: {str(e)}")
                    return {
                        "vendor": "Unknown", 
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "total": 0,
                        "line_items": []
                    }
            
            # Use ThreadPoolExecutor for timeouts
            with ThreadPoolExecutor() as executor:
                # Step 1: Veryfi OCR with timeout
                future = executor.submit(process_with_veryfi)
                try:
                    veryfi_result = future.result(timeout=30)  # 30 second timeout
                    raw_ocr_text = veryfi_result.get('ocr_text', '')
                    app.logger.info(f"Texte OCR extrait avec Veryfi: {len(raw_ocr_text)} caractères")
                except TimeoutError:
                    app.logger.error("Veryfi processing timed out after 30 seconds")
                    veryfi_result = {"ocr_text": "", "error": "Timeout during processing"}
                    raw_ocr_text = ""
                except Exception as e:
                    app.logger.error(f"Exception during Veryfi processing: {str(e)}")
                    veryfi_result = {"ocr_text": "", "error": str(e)}
                    raw_ocr_text = ""
                
                # Fallback to Tesseract if Veryfi fails
                if not raw_ocr_text:
                    app.logger.info("Pas de texte retourné par Veryfi, recours à Tesseract")
                    future = executor.submit(extract_with_tesseract)
                    try:
                        raw_ocr_text = future.result(timeout=20)  # 20 second timeout
                        app.logger.info(f"Texte OCR extrait avec Tesseract: {len(raw_ocr_text)} caractères")
                    except TimeoutError:
                        app.logger.error("Tesseract extraction timed out")
                        raw_ocr_text = "Error: OCR timeout"
                    except Exception as e:
                        app.logger.error(f"Exception during Tesseract extraction: {str(e)}")
                        raw_ocr_text = f"Error: {str(e)}"
                
                # Step 2: Clean text with Mistral
                future = executor.submit(clean_with_mistral, raw_ocr_text)
                try:
                    cleaned_text = future.result(timeout=20)  # 20 second timeout
                    app.logger.info("Nettoyage du texte avec Mistral terminé")
                except TimeoutError:
                    app.logger.error("Mistral text cleaning timed out")
                    cleaned_text = raw_ocr_text
                except Exception as e:
                    app.logger.error(f"Exception during Mistral text cleaning: {str(e)}")
                    cleaned_text = raw_ocr_text
                
                # Step 3: Classify with Mistral
                future = executor.submit(classify_with_mistral, cleaned_text)
                try:
                    structured_data = future.result(timeout=20)  # 20 second timeout
                    app.logger.info("Classification des données avec Mistral terminée")
                except TimeoutError:
                    app.logger.error("Mistral classification timed out")
                    structured_data = {
                        "vendor": "Unknown (timeout)", 
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "total": 0,
                        "line_items": []
                    }
                except Exception as e:
                    app.logger.error(f"Exception during Mistral classification: {str(e)}")
                    structured_data = {
                        "vendor": "Unknown (error)", 
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "total": 0,
                        "line_items": []
                    }
            
            # Combine results
            combined_result = {
                "vendor": structured_data.get("vendor", veryfi_result.get("vendor_name", "Unknown")),
                "date": structured_data.get("date", veryfi_result.get("date", "")),
                "total": structured_data.get("total", veryfi_result.get("total", 0)),
                "line_items": structured_data.get("line_items", veryfi_result.get("line_items", [])),
                "category": structured_data.get("category", veryfi_result.get("category", "Uncategorized")),
                "payment_method": structured_data.get("payment_method", veryfi_result.get("payment_type", "Unknown")),
                "store_address": structured_data.get("store_address", veryfi_result.get("vendor_address", "")),
                "store_phone": structured_data.get("store_phone", veryfi_result.get("vendor_phone", "")),
                "store_email": structured_data.get("store_email", veryfi_result.get("vendor_email", "")),
                "store_website": structured_data.get("store_website", veryfi_result.get("vendor_website", "")),
                "tax": structured_data.get("tax", veryfi_result.get("tax", 0)),
                "subtotal": structured_data.get("subtotal", veryfi_result.get("subtotal", 0)),
                "siret": structured_data.get("siret", ""),
                "tva_number": structured_data.get("tva_number", ""),
                "capital": structured_data.get("capital", ""),
                "naf_code": structured_data.get("naf_code", ""),
                "cashier": structured_data.get("cashier", ""),
                "client_type": structured_data.get("client_type", ""),
                "ocr_text": raw_ocr_text,
                "cleaned_text": cleaned_text,
                "veryfi_data": veryfi_result,
                "storage_type": "Google Cloud Storage"
            }
            
            # Get client ID if user is logged in
            client_id = None
            if session.get('logged_in') and session.get('client_id'):
                client_id = session.get('client_id')
                app.logger.info(f"Client connecté ID: {client_id} - {session.get('client_name', '')}")
                combined_result["client_id"] = client_id
            
            # Generate receipt ID
            current_date = datetime.now().strftime('%Y%m%d_%H%M%S')
            ticket_uuid = str(uuid.uuid4())[:8]
            receipt_id = f"receipt_{current_date}_{ticket_uuid}"
            app.logger.info(f"ID de ticket généré: {receipt_id}")
            
            # Upload image to GCS with timeout
            image_blob_name = f"receipts/images/{receipt_id}.jpg"
            image_url = None
            
            try:
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(storage_manager.upload_file, filepath, image_blob_name)
                    image_url = future.result(timeout=30)  # 30 second timeout
                    combined_result["image_url"] = image_url
                    app.logger.info(f"Image sauvegardée dans GCP: {image_blob_name}")
            except TimeoutError:
                app.logger.error("GCS image upload timed out")
                combined_result["image_url"] = f"/static/uploads/{filename}"
            except Exception as e:
                app.logger.error(f"Error uploading image to GCS: {str(e)}")
                combined_result["image_url"] = f"/static/uploads/{filename}"
            
            combined_result["receipt_id"] = receipt_id
            combined_result["processed_at"] = datetime.now().isoformat()
            
            # Save JSON data to GCS with timeout
            json_blob_name = f"receipts/json/{receipt_id}.json"
            json_data = json.dumps(combined_result, indent=2, default=str)
            
            try:
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(storage_manager.upload_from_string, json_data, json_blob_name, "application/json")
                    future.result(timeout=20)  # 20 second timeout
                    app.logger.info(f"Données du ticket sauvegardées dans GCP Storage avec l'ID: {receipt_id}")
            except TimeoutError:
                app.logger.error("GCS JSON upload timed out")
            except Exception as e:
                app.logger.error(f"Error uploading JSON to GCS: {str(e)}")
            
            # Save JSON locally as fallback
            json_dir = os.path.join(app.config['DATA_DIR'], 'json')
            os.makedirs(json_dir, exist_ok=True)
            local_json_path = os.path.join(json_dir, f"{receipt_id}.json")
            with open(local_json_path, 'w') as f:
                f.write(json_data)
            app.logger.info(f"Données du ticket sauvegardées localement: {local_json_path}")
            
            # Integrate with loyalty database
            try:
                db_success, transaction_id, db_message = db_integrator.process_receipt_data(
                    combined_result, 
                    image_url or f"/static/uploads/{filename}",
                    client_id
                )
                
                if db_success:
                    app.logger.info(f"Ticket intégré dans la base de données de fidélité. ID Transaction: {transaction_id}")
                    combined_result["loyalty_transaction_id"] = transaction_id
                    
                    # Update JSON with transaction ID
                    json_data = json.dumps(combined_result, indent=2, default=str)
                    try:
                        storage_manager.upload_from_string(json_data, json_blob_name, "application/json")
                    except Exception as e:
                        app.logger.error(f"Error updating JSON in GCS: {str(e)}")
                    
                    # Update local JSON
                    with open(local_json_path, 'w') as f:
                        f.write(json_data)
                    
                    if session.get('logged_in'):
                        flash("Votre ticket a été associé à votre compte et vos points ont été mis à jour!", "success")
                else:
                    app.logger.error(f"Échec de l'intégration du ticket avec la base de données de fidélité: {db_message}")
                    
                    if session.get('logged_in'):
                        flash(f"Erreur lors de l'association du ticket à votre compte: {db_message}", "danger")
            except Exception as e:
                app.logger.error(f"Exception during loyalty database integration: {str(e)}")
                db_success = False
                transaction_id = None
            
            # Try to remove local file
            try:
                if os.path.exists(filepath) and image_url and image_url.startswith("https://"):
                    os.remove(filepath)
                    app.logger.info(f"Fichier local supprimé: {filepath}")
            except Exception as e:
                app.logger.error(f"Error removing local file: {str(e)}")
            
            app.logger.info(f"Traitement du ticket terminé avec succès")
            
            return jsonify({
                'success': True, 
                'receipt_id': receipt_id,
                'db_integration': db_success,
                'transaction_id': transaction_id if db_success else None,
                'client_id': client_id,
                'storage_type': "Google Cloud Storage"
            })
            
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement du ticket: {str(e)}")
            app.logger.exception("Exception détaillée")
                
            # Ensure file is cleaned up
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass
                
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/history')
def history():
    # This route displays all receipts for users
    app.logger.info("History page accessed")
    
    if not session.get('logged_in'):
        app.logger.warning("Unauthenticated history access attempt")
        flash("Veuillez vous connecter pour accéder à l'historique", "warning")
        return redirect(url_for('login'))
    
    # Show all receipts
    try:
        # Get receipts from GCP Storage
        app.logger.info("Fetching receipts from GCP Storage")
        receipts = storage_manager.list_receipts(limit=100)
        app.logger.info(f"Retrieved {len(receipts)} receipts from GCP Storage")
        
        # Filtrer les receipts None ou invalides
        valid_receipts = [r for r in receipts if r is not None]
        
        # Sort receipts by date (most recent first)
        # Utiliser une fonction de tri sécurisée qui gère les valeurs manquantes
        def safe_sort_key(receipt):
            if not receipt or 'processed_at' not in receipt or receipt['processed_at'] is None:
                return ""  # Valeur par défaut pour le tri si processed_at est absent ou None
            return receipt['processed_at']
            
        valid_receipts.sort(key=safe_sort_key, reverse=True)
        
        # Get storage status for display
        storage_info = storage_manager.get_storage_status()
        
        return render_template('history.html', 
                              receipts=valid_receipts, 
                              storage_info=storage_info,
                              db_type="Google Cloud Storage")
    except Exception as e:
        app.logger.error(f"Error loading receipts: {str(e)}")
        flash(f"Erreur lors du chargement des tickets: {str(e)}", "danger")
        return render_template('history.html', receipts=[], storage_info={})

@app.route('/receipt/<receipt_id>')
def receipt_detail(receipt_id):
    app.logger.info(f"Receipt detail accessed: {receipt_id}")
    
    try:
        # Get receipt data from GCP Storage
        app.logger.info(f"Fetching receipt data from GCP: {receipt_id}")
        receipt_data = storage_manager.get_receipt_data(receipt_id)
        
        if not receipt_data:
            app.logger.warning(f"Receipt not found: {receipt_id}")
            flash("Ticket non trouvé", "warning")
            return redirect(url_for('history'))
        
        app.logger.info(f"Receipt data retrieved successfully. Fields: {list(receipt_data.keys())}")
        
        # Ensure all expected fields have default values
        # This prevents NoneType errors when accessing fields
        default_fields = {
            'vendor': 'Unknown',
            'date': '',
            'total': 0,
            'subtotal': 0,
            'tax': 0,
            'line_items': [],
            'client_id': None,
            'loyalty_transaction_id': None,
            'image_url': '/static/placeholder.jpg',
            'ocr_text': '',
            'cleaned_text': '',
        }
        
        # Add default values for any missing fields
        for field, default_value in default_fields.items():
            if field not in receipt_data or receipt_data[field] is None:
                app.logger.info(f"Setting default value for missing field: {field}")
                receipt_data[field] = default_value
        
        # Deserialize line items if needed
        if isinstance(receipt_data.get('line_items'), str):
            app.logger.info("Deserializing line_items from string")
            try:
                receipt_data['line_items'] = json.loads(receipt_data['line_items'])
                app.logger.info(f"Successfully deserialized {len(receipt_data['line_items'])} line items")
            except (json.JSONDecodeError, KeyError) as e:
                app.logger.error(f"Error deserializing line_items: {str(e)}")
                receipt_data['line_items'] = []
        
        # S'assurer que line_items est toujours une liste
        if not isinstance(receipt_data.get('line_items'), list):
            app.logger.warning("line_items is not a list, converting to empty list")
            receipt_data['line_items'] = []
        
        # Get loyalty transaction info if available
        loyalty_transaction = None
        transaction_id = receipt_data.get('loyalty_transaction_id')
        if transaction_id:
            app.logger.info(f"Fetching loyalty transaction: {transaction_id}")
            loyalty_transaction = get_loyalty_transaction(transaction_id)
            
            if loyalty_transaction:
                app.logger.info("Loyalty transaction data retrieved successfully")
            else:
                app.logger.warning(f"No loyalty transaction found for ID: {transaction_id}")
        
        # Get storage status for display
        storage_info = storage_manager.get_storage_status()
        
        app.logger.info("Rendering receipt_detail.html template")
        return render_template('receipt_detail.html', 
                            receipt=receipt_data,
                            image_url=receipt_data.get('image_url'),
                            loyalty_transaction=loyalty_transaction,
                            storage_info=storage_info,
                            db_type="Google Cloud Storage")
    except Exception as e:
        app.logger.error(f"Error viewing receipt: {str(e)}")
        app.logger.exception("Exception détaillée")
        traceback.print_exc() # Print full traceback to console
        flash(f"Erreur lors de l'affichage du ticket: {str(e)}", "danger")
        return redirect(url_for('history'))
    
def get_loyalty_transaction(transaction_id):
    """Get transaction details from loyalty database"""
    try:
        if db_integrator.connect():
            # Log for debugging
            app.logger.info(f"Fetching transaction with ID: {transaction_id}")
            
            query = """
            SELECT t.transaction_id, t.date_transaction, t.montant_total, 
                   t.points_gagnes, t.points_utilises, c.nom as client_nom, 
                   c.prenom as client_prenom, cf.numero_carte, cf.niveau_fidelite,
                   pv.nom as magasin_nom
            FROM transactions t
            LEFT JOIN clients c ON t.client_id = c.client_id
            LEFT JOIN cartes_fidelite cf ON t.client_id = cf.client_id
            LEFT JOIN points_vente pv ON t.magasin_id = pv.magasin_id
            WHERE t.transaction_id = ?
            """
            db_integrator.cursor.execute(query, (transaction_id,))
            transaction = db_integrator.cursor.fetchone()
            
            # Get transaction details (products)
            if transaction:
                transaction = dict(transaction)
                
                details_query = """
                SELECT dt.detail_id, dt.quantite, dt.prix_unitaire, dt.montant_ligne,
                       p.nom as produit_nom
                FROM details_transactions dt
                LEFT JOIN produits p ON dt.produit_id = p.produit_id
                WHERE dt.transaction_id = ?
                """
                db_integrator.cursor.execute(details_query, (transaction_id,))
                details = [dict(row) for row in db_integrator.cursor.fetchall()]
                transaction['details'] = details
                
            db_integrator.disconnect()
            return transaction
    except Exception as e:
        app.logger.error(f"Error fetching loyalty transaction: {str(e)}")
    
    return None

@app.route('/data/images/<filename>')
def data_images(filename):
    # This route now creates a signed URL for GCP Storage objects
    try:
        blob_name = f"receipts/images/{filename}"
        if storage_manager.blob_exists(blob_name):
            blob = storage_manager.bucket.blob(blob_name)
            # Generate a signed URL that works with uniform bucket-level access
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(days=1),
                method="GET"
            )
            # Redirect to the signed URL
            return redirect(signed_url)
            
        return "Image not found in GCP Storage", 404
    except Exception as e:
        app.logger.error(f"Error serving image from GCP: {str(e)}")
        return f"Error serving image from GCP: {str(e)}", 500

@app.route('/transactions')
def transactions_list():
    """List all transactions from the loyalty database"""
    if not session.get('logged_in'):
        flash("Veuillez vous connecter pour accéder aux transactions", "warning")
        return redirect(url_for('login'))
        
    transactions = []
    
    try:
        if db_integrator.connect():
            query = """
            SELECT t.transaction_id, t.date_transaction, t.montant_total, 
                   t.points_gagnes, c.nom as client_nom, c.prenom as client_prenom,
                   pv.nom as magasin_nom
            FROM transactions t
            LEFT JOIN clients c ON t.client_id = c.client_id
            LEFT JOIN points_vente pv ON t.magasin_id = pv.magasin_id
            ORDER BY t.date_transaction DESC
            LIMIT 100
            """
            db_integrator.cursor.execute(query)
            transactions = [dict(row) for row in db_integrator.cursor.fetchall()]
            db_integrator.disconnect()
    except Exception as e:
        app.logger.error(f"Error fetching transactions: {str(e)}")
    
    return render_template('transactions.html', transactions=transactions)

@app.route('/transaction/<int:transaction_id>')
def transaction_detail(transaction_id):
    """Show details of a specific transaction"""
    transaction = get_loyalty_transaction(transaction_id)
    
    # Vérifier si l'utilisateur a accès à cette transaction
    if transaction:
        """
# Si l'utilisateur est connecté et que la transaction appartient à un autre client
        if session.get('logged_in') and transaction.get('client_id') != session.get('client_id'):
            # Vérifier s'il s'agit de l'administrateur
            if not session.get('is_admin', False):
                flash("Vous n'avez pas accès à cette transaction", "warning")
                return redirect(url_for('my_receipts')) """
        
        return render_template('transaction_detail.html', transaction=transaction)
    
    return "Transaction not found", 404

@app.route('/clients')
def clients_list():
    """List all clients from the loyalty database - accès admin uniquement"""
    # Si l'utilisateur est connecté mais n'est pas admin, rediriger vers profil
    if session.get('logged_in') and not session.get('is_admin', False):
        return redirect(url_for('profile'))
        
    clients = []
    
    try:
        if db_integrator.connect():
            query = """
            SELECT c.client_id, c.nom, c.prenom, c.email, c.date_inscription,
                   cf.numero_carte, cf.niveau_fidelite, cf.points_actuels
            FROM clients c
            LEFT JOIN cartes_fidelite cf ON c.client_id = cf.client_id
            WHERE c.statut = 'actif'
            ORDER BY c.date_inscription DESC
            LIMIT 100
            """
            db_integrator.cursor.execute(query)
            clients = [dict(row) for row in db_integrator.cursor.fetchall()]
            db_integrator.disconnect()
    except Exception as e:
        app.logger.error(f"Error fetching clients: {str(e)}")
    
    return render_template('clients.html', clients=clients)

@app.route('/client/<int:client_id>')
def client_detail(client_id):
    """Show details of a specific client"""
    # Si l'utilisateur est connecté, vérifier l'accès
    if session.get('logged_in'):
        # Si ce n'est pas son propre profil et qu'il n'est pas admin
        if client_id != session.get('client_id') and not session.get('is_admin', False):
            flash("Vous n'avez pas accès à ce profil client", "warning")
            return redirect(url_for('profile'))
            
    client = None
    transactions = []
    
    try:
        if db_integrator.connect():
            # Get client info
            query = """
            SELECT c.client_id, c.nom, c.prenom, c.email, c.telephone, 
                   c.adresse, c.code_postal, c.ville, c.date_inscription,
                   cf.numero_carte, cf.niveau_fidelite, cf.points_actuels, 
                   cf.date_expiration
            FROM clients c
            LEFT JOIN cartes_fidelite cf ON c.client_id = cf.client_id
            WHERE c.client_id = ?
            """
            db_integrator.cursor.execute(query, (client_id,))
            client = db_integrator.cursor.fetchone()
            
            if client:
                client = dict(client)
                
                # Get client transactions
                trans_query = """
                SELECT t.transaction_id, t.date_transaction, t.montant_total, 
                       t.points_gagnes, pv.nom as magasin_nom
                FROM transactions t
                LEFT JOIN points_vente pv ON t.magasin_id = pv.magasin_id
                WHERE t.client_id = ?
                ORDER BY t.date_transaction DESC
                LIMIT 20
                """
                db_integrator.cursor.execute(trans_query, (client_id,))
                transactions = [dict(row) for row in db_integrator.cursor.fetchall()]
                
                # Get points history
                points_query = """
                SELECT h.date_operation, h.type_operation, h.points, h.description, h.solde_apres
                FROM historique_points h
                WHERE h.client_id = ?
                ORDER BY h.date_operation DESC
                LIMIT 20
                """
                db_integrator.cursor.execute(points_query, (client_id,))
                points_history = [dict(row) for row in db_integrator.cursor.fetchall()]
                client['points_history'] = points_history
                
            db_integrator.disconnect()
    except Exception as e:
        app.logger.error(f"Error fetching client details: {str(e)}")
    
    if client:
        return render_template('client_detail.html', client=client, transactions=transactions)
    
    return "Client not found", 404

@app.route('/health')
def health_check():
    """Health check endpoint to verify the app is running correctly"""
    try:
        # Check key components
        health_info = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0",
            "components": {
                "app": "ok",
                "database": "unknown",
                "storage": "unknown"
            }
        }
        
        # Check database connection
        try:
            db_status = db_integrator.connect()
            if db_status:
                health_info["components"]["database"] = "ok"
                db_integrator.disconnect()
            else:
                health_info["components"]["database"] = "error"
                health_info["status"] = "degraded"
        except Exception as e:
            health_info["components"]["database"] = f"error: {str(e)}"
            health_info["status"] = "degraded"
        
        # Check storage connection
        try:
            storage_status = storage_manager.get_storage_status()
            if storage_status.get("mode") == "mock":
                health_info["components"]["storage"] = "mock (degraded)"
                health_info["status"] = "degraded"
            else:
                health_info["components"]["storage"] = "ok"
        except Exception as e:
            health_info["components"]["storage"] = f"error: {str(e)}"
            health_info["status"] = "degraded"
        
        return jsonify(health_info)
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    try:
        # Structured initialization
        print("\n\n==== DÉMARRAGE DE L'APPLICATION ====")
        print("Starting initialization...")
        print("1. Setting up configuration...")
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        # Get all available network interfaces for more reliable connection info
        import socket
        def get_ip_addresses():
            ip_list = []
            interfaces = socket.getaddrinfo(socket.gethostname(), None)
            for interface in interfaces:
                ip = interface[4][0]
                # Filter out loopback addresses and IPv6
                if not ip.startswith('127.') and ':' not in ip:
                    ip_list.append(ip)
            return ip_list
            
        network_ips = get_ip_addresses()
        
        print(f"Hostname: {hostname}")
        print(f"Available IP addresses:")
        for ip in network_ips:
            print(f"  - http://{ip}:5000")
        
        print("4. Starting server...")
        print(f"\n* Access the app from devices on your network:")
        for ip in network_ips:
            print(f"* http://{ip}:5000")
        print(f"\n* Storage Configuration:")
        print(f"* Using Google Cloud Storage (no fallback)")
        print(f"* Bucket: {app.config['GCP_BUCKET_NAME']}\n")
        
        # Ensure our logs also go to the console
        print("==== APPLICATION LOGS WILL APPEAR BELOW ====")
        
        # Use logging instead of both print and logging
        logging.info("==== APPLICATION STARTING ====")
        logging.info(f"Server available at: http://{local_ip}:5000")
        
        # Important to avoid debug reloader causing issues
        # The debug reloader can cause duplicate initialization
        use_debugger = os.environ.get('FLASK_DEBUG', 'false').lower() != 'false'
        logging.info(f"Debug mode: {use_debugger}")
        
        # Start the app
        app.run(
            host='0.0.0.0', 
            port=5000, 
            debug=use_debugger, 
            use_reloader=False  # Important to disable reloader for our case
        )
    except Exception as e:
        print(f"FATAL ERROR during startup: {str(e)}")
        traceback.print_exc()