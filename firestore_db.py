from google.cloud import firestore
import os
import json
from datetime import datetime
import logging

class FirestoreManager:
    """
    Class to manage Firestore NoSQL database operations for receipt data
    """
    def __init__(self, credentials_path):
        """
        Initialize Firestore client
        :param credentials_path: Path to service account credentials JSON file
        """
        self.credentials_path = credentials_path
        self._db = None
        self.logger = logging.getLogger(__name__)
        
        # Set environment variable for authentication
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        # Initialize Firestore client
        try:
            self.db
            self.logger.info("Firestore initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Firestore: {str(e)}")
            raise
        
    @property
    def db(self):
        """Lazy initialization of Firestore client"""
        if self._db is None:
            try:
                self._db = firestore.Client()
                self.logger.info(f"Firestore client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Firestore client: {str(e)}")
                raise
        return self._db
    
    def save_receipt_data(self, receipt_data, transaction_id=None):
        """
        Save receipt data to Firestore
        :param receipt_data: Dictionary containing receipt data
        :param transaction_id: Optional transaction ID to link with the receipt
        :return: Receipt ID
        """
        try:
            # If receipt_id not provided, generate one
            receipt_id = receipt_data.get('receipt_id')
            if not receipt_id:
                # Generate a receipt ID based on date and random ID
                current_date = datetime.now().strftime('%Y%m%d_%H%M%S')
                receipt_id = f"receipt_{current_date}"
                receipt_data['receipt_id'] = receipt_id
            
            # Add timestamp
            receipt_data['processed_at'] = datetime.now().isoformat()
            
            # Add transaction ID if provided
            if transaction_id:
                receipt_data['loyalty_transaction_id'] = transaction_id
            
            # Save to Firestore
            receipt_ref = self.db.collection('receipts').document(receipt_id)
            receipt_ref.set(receipt_data)
            
            self.logger.info(f"Receipt data saved to Firestore with ID: {receipt_id}")
            return receipt_id
        except Exception as e:
            self.logger.error(f"Error saving receipt data to Firestore: {str(e)}")
            raise
    
    def get_receipt_data(self, receipt_id):
        """
        Get receipt data from Firestore
        :param receipt_id: Receipt ID
        :return: Receipt data as dictionary
        """
        try:
            receipt_ref = self.db.collection('receipts').document(receipt_id)
            receipt_doc = receipt_ref.get()
            
            if not receipt_doc.exists:
                self.logger.warning(f"Receipt {receipt_id} not found in Firestore")
                return None
                
            receipt_data = receipt_doc.to_dict()
            return receipt_data
        except Exception as e:
            self.logger.error(f"Error getting receipt data from Firestore: {str(e)}")
            raise
    
    def update_receipt_with_transaction(self, receipt_id, transaction_id):
        """
        Update receipt with transaction ID
        :param receipt_id: Receipt ID
        :param transaction_id: Transaction ID
        :return: True if successful
        """
        try:
            receipt_ref = self.db.collection('receipts').document(receipt_id)
            receipt_ref.update({
                'loyalty_transaction_id': transaction_id,
                'updated_at': datetime.now().isoformat()
            })
            self.logger.info(f"Receipt {receipt_id} updated with transaction ID: {transaction_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating receipt with transaction ID: {str(e)}")
            raise
    
    def list_receipts(self, limit=100, client_id=None):
        """
        List receipts, optionally filtered by client_id
        :param limit: Maximum number of receipts to return
        :param client_id: Optional client ID to filter by
        :return: List of receipt data dictionaries
        """
        try:
            query = self.db.collection('receipts')
            
            # If client_id is specified, filter by it
            if client_id is not None:
                query = query.where('client_id', '==', client_id)
            
            # Order by processed_at in descending order and limit results
            query = query.order_by('processed_at', direction=firestore.Query.DESCENDING).limit(limit)
            
            # Execute query and convert results to dictionaries
            results = query.stream()
            receipts = [doc.to_dict() for doc in results]
            
            self.logger.info(f"Retrieved {len(receipts)} receipts from Firestore")
            return receipts
        except Exception as e:
            self.logger.error(f"Error listing receipts from Firestore: {str(e)}")
            raise
    
    def delete_receipt(self, receipt_id):
        """
        Delete a receipt from Firestore
        :param receipt_id: Receipt ID
        :return: True if successful
        """
        try:
            receipt_ref = self.db.collection('receipts').document(receipt_id)
            receipt_ref.delete()
            self.logger.info(f"Receipt {receipt_id} deleted from Firestore")
            return True
        except Exception as e:
            self.logger.error(f"Error deleting receipt from Firestore: {str(e)}")
            raise
            
    def get_receipts_by_vendor(self, vendor_name, limit=20):
        """
        Get receipts by vendor name
        :param vendor_name: Vendor name to search for
        :param limit: Maximum number of results to return
        :return: List of receipt data dictionaries
        """
        try:
            query = self.db.collection('receipts').where('vendor', '==', vendor_name).limit(limit)
            results = query.stream()
            receipts = [doc.to_dict() for doc in results]
            self.logger.info(f"Retrieved {len(receipts)} receipts for vendor: {vendor_name}")
            return receipts
        except Exception as e:
            self.logger.error(f"Error getting receipts by vendor: {str(e)}")
            raise
            
    def get_receipts_by_date_range(self, start_date, end_date, limit=100):
        """
        Get receipts within a date range
        :param start_date: Start date (string in ISO format)
        :param end_date: End date (string in ISO format)
        :param limit: Maximum number of results to return
        :return: List of receipt data dictionaries
        """
        try:
            query = self.db.collection('receipts').where('date', '>=', start_date).where('date', '<=', end_date).limit(limit)
            results = query.stream()
            receipts = [doc.to_dict() for doc in results]
            self.logger.info(f"Retrieved {len(receipts)} receipts between {start_date} and {end_date}")
            return receipts
        except Exception as e:
            self.logger.error(f"Error getting receipts by date range: {str(e)}")
            raise 