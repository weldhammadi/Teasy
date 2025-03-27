import os
import json
import time
import pandas as pd
from datetime import datetime
import veryfi  # Using the Veryfi client library
import requests
from mistral_llm_service import MistralLLMService

class ReceiptProcessor:
    def __init__(self):
        """Initialize the Veryfi client."""
        self.client = veryfi.Client(
            client_id=os.getenv("VERYFI_CLIENT_ID"),
            client_secret=os.getenv("VERYFI_CLIENT_SECRET"),
            username=os.getenv("VERYFI_USERNAME"),
            api_key=os.getenv("VERYFI_API_KEY")
        )
        
        self.llm_service = MistralLLMService()
        self._ensure_directories()
        self._verify_mistral_connection()

    def _ensure_directories(self):
        """Ensure required directories exist."""
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.images_dir = os.path.join(self.base_dir, 'data', 'images')
        self.csv_dir = os.path.join(self.base_dir, 'data', 'csv')
        self.json_dir = os.path.join(self.base_dir, 'data', 'json')
        
        for directory in [self.images_dir, self.csv_dir, self.json_dir]:
            os.makedirs(directory, exist_ok=True)

    def process_image(self, image_path):
        """Process receipt using Veryfi API then enhance with LLM"""
        # Get raw OCR data from Veryfi
        veryfi_data = self._call_veryfi_api(image_path)
        ocr_text = veryfi_data.get('ocr_text', '')
        
        # If OCR text is empty, create a simple text representation from the line items
        if not ocr_text and veryfi_data.get('line_items'):
            vendor_name = veryfi_data.get('vendor', {}).get('name', veryfi_data.get('vendor_name', 'Unknown'))
            date = veryfi_data.get('date', 'Unknown')
            
            # Build our own OCR text from the line items
            ocr_text = f"{vendor_name}\n{date}\n\n"
            
            for item in veryfi_data.get('line_items', []):
                description = item.get('description', 'Unknown item')
                quantity = item.get('quantity', 1)
                price = item.get('price', 0)
                total = quantity * price
                
                ocr_text += f"{description} {quantity}x{price:.2f} Total: {total:.2f}\n"
                
            ocr_text += f"\nTOTAL: {veryfi_data.get('total', 0):.2f}"
        
        # Add the OCR text to the result
        veryfi_data['ocr_text'] = ocr_text
        
        return veryfi_data

    def _call_veryfi_api(self, image_path):
        """Call Veryfi API to process receipt image"""
        try:
            # Use the client directly instead of credentials dict
            with open(image_path, 'rb') as image_file:
                response = self.client.process_document(
                    file_path=image_path,
                    categories=["Grocery", "Food", "Restaurant"]
                )
                
            return response
        except Exception as e:
            print(f"Veryfi API error: {str(e)}")
            raise Exception(f"Veryfi API error: {str(e)}")

    def save_receipt_data(self, result, image_path, base_dir):
        """Save processed data with LLM-enhanced items"""
        receipt_id = f"receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Prepare data
        data = {
            "receipt_id": receipt_id,
            "vendor": result.get("vendor", "Unknown"),
            "date": result.get("date", ""),
            "total": result.get("total", 0),
            "line_items": json.dumps(result.get("line_items", [])),
            "text_brut": result.get("ocr_text", ""),
            "category": result.get("category", ""),
            "payment_method": result.get("payment_method", ""),
            "processed_at": datetime.now().isoformat()
        }

        # Create directories
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(os.path.join(data_dir, "csv"), exist_ok=True)
        os.makedirs(os.path.join(data_dir, "json"), exist_ok=True)
        os.makedirs(os.path.join(data_dir, "images"), exist_ok=True)

        # Save CSV
        csv_path = os.path.join(data_dir, "csv", f"{receipt_id}.csv")
        pd.DataFrame([data]).to_csv(csv_path, index=False)

        # Save JSON
        json_path = os.path.join(data_dir, "json", f"{receipt_id}.json")
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

        # Save image
        image_filename = os.path.join(data_dir, "images", f"{receipt_id}.jpg")
        os.rename(image_path, image_filename)

        return receipt_id

    def _verify_mistral_connection(self):
        """Verify Mistral API connectivity"""
        test_prompt = '{"status": "ok"}'
        response = self.llm_service.generate(test_prompt)
        if not response or "ok" not in response:
            raise ConnectionError("Failed to connect to Mistral API")
