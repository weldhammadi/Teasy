from google.cloud import storage
import os
import json
import pandas as pd
from datetime import datetime, timedelta
import logging
import io
import shutil
from pathlib import Path

class GCPStorageManager:
    """
    Class to manage GCP Storage operations for receipt data
    """
    def __init__(self, bucket_name, credentials_path, use_local_fallback=False):
        """
        Initialize GCP Storage client
        :param bucket_name: Name of the GCP bucket
        :param credentials_path: Path to service account credentials JSON file
        :param use_local_fallback: Whether to use local storage as fallback when GCP fails (default: False)
        """
        self.bucket_name = bucket_name
        self.credentials_path = credentials_path
        self._client = None
        self._bucket = None
        self.logger = logging.getLogger(__name__)
        self.use_local_fallback = use_local_fallback
        self.use_gcp = True  # Flag to indicate if GCP should be used
        
        # Set environment variable for authentication
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        # Local storage paths (only used if fallback is enabled)
        if use_local_fallback:
            self.local_base_path = Path(os.path.dirname(os.path.abspath(__file__))) / 'local_storage'
            self.local_json_path = self.local_base_path / 'receipts' / 'json'
            self.local_csv_path = self.local_base_path / 'receipts' / 'csv'
            self.local_images_path = self.local_base_path / 'receipts' / 'images'
            
            # Create local directories if using fallback
            os.makedirs(self.local_json_path, exist_ok=True)
            os.makedirs(self.local_csv_path, exist_ok=True)
            os.makedirs(self.local_images_path, exist_ok=True)
            
        # Try to initialize GCP client
        try:
            self.client
            self.bucket
            self.logger.info("GCP Storage initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize GCP Storage: {str(e)}")
            raise
        
    @property
    def client(self):
        """Lazy initialization of storage client"""
        if self._client is None and self.use_gcp:
            try:
                self._client = storage.Client()
                self.logger.info(f"GCP Storage client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize GCP Storage client: {str(e)}")
                raise
        return self._client
    
    @property
    def bucket(self):
        """Lazy initialization of bucket"""
        if self._bucket is None and self.use_gcp:
            try:
                self._bucket = self.client.bucket(self.bucket_name)
                self.logger.info(f"Connected to bucket: {self.bucket_name}")
            except Exception as e:
                self.logger.error(f"Failed to connect to bucket {self.bucket_name}: {str(e)}")
                raise
        return self._bucket
    
    def upload_file(self, source_file_path, destination_blob_name):
        """
        Upload a file to the bucket
        :param source_file_path: Path to source file
        :param destination_blob_name: Name of the destination blob
        :return: URL for accessing the uploaded file
        """
        try:
            blob = self.bucket.blob(destination_blob_name)
            blob.upload_from_filename(source_file_path)
            self.logger.info(f"File {source_file_path} uploaded to {destination_blob_name}")
            
            try:
                # Generate a signed URL that works with uniform bucket-level access
                url = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(days=7),
                    method="GET"
                )
                self.logger.info(f"Generated signed URL for {destination_blob_name}")
                return url
            except Exception as sign_error:
                self.logger.warning(f"Could not generate signed URL: {str(sign_error)}. Using default URL.")
                # Fallback to regular URL if signed URL fails
                return f"https://storage.googleapis.com/{self.bucket_name}/{destination_blob_name}"
        except Exception as e:
            self.logger.error(f"Failed to upload file {source_file_path}: {str(e)}")
            raise
    
    def upload_from_string(self, data, destination_blob_name, content_type="application/json"):
        """
        Upload data from a string to the bucket
        :param data: String data to upload
        :param destination_blob_name: Name of the destination blob
        :param content_type: Content type of the data
        :return: URL for accessing the uploaded file
        """
        try:
            blob = self.bucket.blob(destination_blob_name)
            blob.upload_from_string(data, content_type=content_type)
            self.logger.info(f"Data uploaded to {destination_blob_name}")
            
            try:
                # Generate a signed URL that works with uniform bucket-level access
                url = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(days=7),
                    method="GET"
                )
                self.logger.info(f"Generated signed URL for {destination_blob_name}")
                return url
            except Exception as sign_error:
                self.logger.warning(f"Could not generate signed URL: {str(sign_error)}. Using default URL.")
                # Fallback to regular URL if signed URL fails
                return f"https://storage.googleapis.com/{self.bucket_name}/{destination_blob_name}"
        except Exception as e:
            self.logger.error(f"Failed to upload data to {destination_blob_name}: {str(e)}")
            raise
    
    def download_as_string(self, blob_name):
        """
        Download blob content as string
        :param blob_name: Name of the blob to download
        :return: Content as string
        """
        try:
            blob = self.bucket.blob(blob_name)
            return blob.download_as_string().decode('utf-8')
        except Exception as e:
            self.logger.error(f"Failed to download blob {blob_name}: {str(e)}")
            raise
    
    def download_to_file(self, blob_name, destination_file_name):
        """
        Download a blob to a local file
        :param blob_name: Name of the blob to download
        :param destination_file_name: Path to destination file
        :return: True if successful, False otherwise
        """
        try:
            blob = self.bucket.blob(blob_name)
            blob.download_to_filename(destination_file_name)
            self.logger.info(f"Blob {blob_name} downloaded to {destination_file_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to download blob {blob_name}: {str(e)}")
            raise
    
    def list_blobs(self, prefix=None):
        """
        List blobs in the bucket
        :param prefix: Optional prefix to filter blobs
        :return: List of blob names
        """
        try:
            blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
            return [blob.name for blob in blobs]
        except Exception as e:
            self.logger.error(f"Failed to list blobs with prefix {prefix}: {str(e)}")
            raise
    
    def blob_exists(self, blob_name):
        """
        Check if a blob exists
        :param blob_name: Name of the blob to check
        :return: True if blob exists, False otherwise
        """
        try:
            blob = self.bucket.blob(blob_name)
            return blob.exists()
        except Exception as e:
            self.logger.error(f"Failed to check if blob {blob_name} exists: {str(e)}")
            raise
    
    def save_receipt_data(self, receipt_id, receipt_data, image_path=None):
        """
        Save receipt data to GCP Storage
        :param receipt_id: Unique ID for the receipt
        :param receipt_data: Receipt data as dictionary
        :param image_path: Optional local path to receipt image
        :return: Dictionary with URLs for accessing the saved data
        """
        result = {}
        
        # Save JSON data
        json_blob_name = f"receipts/json/{receipt_id}.json"
        json_data = json.dumps(receipt_data, indent=2)
        json_url = self.upload_from_string(json_data, json_blob_name, "application/json")
        result['json_url'] = json_url
        
        # Save image if provided
        if image_path and os.path.exists(image_path):
            image_blob_name = f"receipts/images/{receipt_id}.jpg"
            image_url = self.upload_file(image_path, image_blob_name)
            result['image_url'] = image_url
        
        # Try to create a CSV version
        try:
            # Flatten the data for CSV
            flat_data = {
                'receipt_id': receipt_id,
                'date': receipt_data.get('date', ''),
                'vendor': receipt_data.get('vendor', ''),
                'total': receipt_data.get('total', 0),
                'payment_method': receipt_data.get('payment_method', ''),
                'processed_at': receipt_data.get('processed_at', ''),
            }
            
            df = pd.DataFrame([flat_data])
            csv_data = df.to_csv(index=False)
            csv_blob_name = f"receipts/csv/{receipt_id}.csv"
            csv_url = self.upload_from_string(csv_data, csv_blob_name, "text/csv")
            result['csv_url'] = csv_url
        except Exception as e:
            self.logger.warning(f"Failed to create CSV for receipt {receipt_id}: {str(e)}")
        
        return result
    
    def get_receipt_data(self, receipt_id):
        """
        Get receipt data from GCP Storage
        :param receipt_id: ID of the receipt to retrieve
        :return: Receipt data as dictionary or None if not found
        """
        try:
            json_blob_name = f"receipts/json/{receipt_id}.json"
            if not self.blob_exists(json_blob_name):
                # Try alternative format (with or without receipt_ prefix)
                if receipt_id.startswith('receipt_'):
                    alternative_id = receipt_id[8:]  # Remove 'receipt_' prefix
                else:
                    alternative_id = f"receipt_{receipt_id}"
                json_blob_name = f"receipts/json/{alternative_id}.json"
                
                if not self.blob_exists(json_blob_name):
                    self.logger.warning(f"Receipt {receipt_id} not found in storage")
                    return None
            
            json_data = self.download_as_string(json_blob_name)
            if not json_data:
                self.logger.warning(f"Empty JSON data for receipt {receipt_id}")
                return None
                
            try:
                receipt_data = json.loads(json_data)
                
                # Vérifier que les données sont un dictionnaire valide
                if not isinstance(receipt_data, dict):
                    self.logger.warning(f"Invalid JSON data for receipt {receipt_id} - not a dictionary")
                    return None
                    
                # Add image URL if available
                image_blob_name = f"receipts/images/{receipt_id}.jpg"
                if self.blob_exists(image_blob_name):
                    try:
                        blob = self.bucket.blob(image_blob_name)
                        receipt_data['image_url'] = blob.generate_signed_url(
                            version="v4",
                            expiration=timedelta(days=1),
                            method="GET"
                        )
                    except Exception as img_err:
                        self.logger.warning(f"Error generating signed URL for {receipt_id}: {str(img_err)}")
                
                return receipt_data
            except json.JSONDecodeError as json_err:
                self.logger.error(f"Invalid JSON for receipt {receipt_id}: {str(json_err)}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get receipt data for {receipt_id}: {str(e)}")
            return None
    
    # Correction pour la méthode list_receipts dans gcp_storage.py

    def list_receipts(self, limit=100, client_id=None):
        """
        List all receipts or receipts for a specific client
        :param limit: Maximum number of receipts to return
        :param client_id: Optional client ID to filter receipts
        :return: List of receipt data dictionaries
        """
        try:
            # List JSON files in the receipts/json directory
            json_blobs = self.list_blobs(prefix="receipts/json/")
            receipts = []
            count = 0
            
            for json_blob_name in json_blobs:
                if count >= limit:
                    break
                
                try:
                    # Extract receipt ID from blob name
                    receipt_id = os.path.splitext(os.path.basename(json_blob_name))[0]
                    
                    # Get receipt data
                    json_data = self.download_as_string(json_blob_name)
                    if not json_data:
                        self.logger.warning(f"Empty JSON data for receipt {receipt_id}")
                        continue
                        
                    receipt_data = json.loads(json_data)
                    if not isinstance(receipt_data, dict):
                        self.logger.warning(f"Invalid JSON data for receipt {receipt_id} - not a dictionary")
                        continue
                    
                    # Filter by client_id if specified
                    if client_id is not None:
                        receipt_client_id = receipt_data.get('client_id')
                        # Utiliser une comparaison sécurisée
                        if receipt_client_id is None or str(receipt_client_id) != str(client_id):
                            continue
                    
                    # Add image URL if available
                    image_blob_name = f"receipts/images/{receipt_id}.jpg"
                    if self.blob_exists(image_blob_name):
                        try:
                            blob = self.bucket.blob(image_blob_name)
                            receipt_data['image_url'] = blob.generate_signed_url(
                                version="v4",
                                expiration=timedelta(days=1),
                                method="GET"
                            )
                        except Exception as img_err:
                            self.logger.warning(f"Error generating signed URL for {receipt_id}: {str(img_err)}")
                    
                    receipts.append(receipt_data)
                    count += 1
                except Exception as e:
                    self.logger.warning(f"Error loading receipt {json_blob_name}: {str(e)}")
                    continue
            
            return receipts
        except Exception as e:
            self.logger.error(f"Failed to list receipts: {str(e)}")
            return []  # Retourner une liste vide au lieu de relancer l'exception
    
    def get_storage_status(self):
        """
        Get storage status information
        :return: Dictionary with storage status information
        """
        status = {
            "storage_type": "Google Cloud Storage",
            "bucket_name": self.bucket_name,
            "is_connected": self.use_gcp,
            "fallback_enabled": self.use_local_fallback,
            "using_local_fallback": False,
        }
        
        # Count files
        try:
            json_blobs = self.list_blobs(prefix="receipts/json/")
            status["receipt_count"] = len(json_blobs)
        except Exception as e:
            status["receipt_count"] = 0
            status["error"] = str(e)
        
        return status
    
#----------------------------------------------------------DEBOGAGE ------------------------------------------------

import traceback
import sys

# Redéfinir sys.excepthook pour capturer les traces détaillées des erreurs
def custom_excepthook(exc_type, exc_value, exc_traceback):
    # Format the exception traceback
    traceback_details = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    # Log the exception with traceback
    print("========= EXCEPTION DÉTAILLÉE =========")
    print(traceback_details)
    print("=======================================")
    
    # Log to file
    with open('error_trace.log', 'a') as f:
        f.write("\n\n========= NOUVELLE EXCEPTION =========\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(traceback_details)
        f.write("\n=======================================\n")
    
    # Call the original excepthook
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# Set the custom exception hook
sys.excepthook = custom_excepthook

# Example usage
if __name__ == "__main__":
    # Example code
    storage_manager = GCPStorageManager(
        bucket_name="hackathon-ocr-2025-group1-bucket",
        credentials_path="hackathon-ocr-2025-group1-client.json"
    )
    
    # List all blobs
    blobs = storage_manager.list_blobs()
    print(f"Blobs in bucket: {blobs}")
    
    # Get storage status
    status = storage_manager.get_storage_status()
    print(f"Storage status: {status}") 