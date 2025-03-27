import os
import re
import logging
import numpy as np
import cv2
import pytesseract
from typing import Dict, Any, Optional
import json
from mistral_llm_service import MistralLLMService

class SimplifiedReceiptProcessor:
    def __init__(self, lang: str = 'fra', log_level: int = logging.INFO):
        """
        Initialise un processeur de tickets de caisse avancé
        
        :param lang: Langue pour l'OCR
        :param log_level: Niveau de logging
        """
        # Configuration du logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s: %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Configuration Tesseract
        tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        tessdata_path = r'C:\Program Files\Tesseract-OCR\tessdata'
        
        # Vérifier que l'exécutable existe
        if not os.path.exists(tesseract_path):
            self.logger.error(f"Tesseract n'est pas installé à l'emplacement: {tesseract_path}")
            raise FileNotFoundError(f"L'exécutable Tesseract n'a pas été trouvé: {tesseract_path}")
            
        # Vérifier que le dossier tessdata existe
        if not os.path.exists(tessdata_path):
            self.logger.error(f"Le dossier tessdata n'existe pas: {tessdata_path}")
            raise FileNotFoundError(f"Le dossier tessdata n'a pas été trouvé: {tessdata_path}")
        
        # Vérifier que le fichier de langue existe
        lang_file = os.path.join(tessdata_path, f"{lang}.traineddata")
        if not os.path.exists(lang_file):
            self.logger.error(f"Le fichier de langue '{lang}' n'existe pas: {lang_file}")
            raise FileNotFoundError(f"Le fichier de langue '{lang}.traineddata' n'a pas été trouvé")
        
        # Configurer Tesseract et la variable d'environnement
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        os.environ['TESSDATA_PREFIX'] = tessdata_path
        
        # Initialize Mistral LLM service
        self.llm_service = MistralLLMService()
        
        # Langue
        self.lang = lang
        self.logger.info(f"Tesseract initialisé avec la langue '{lang}' et le dossier tessdata: {tessdata_path}")
        self.logger.info("SimplifiedReceiptProcessor initialized with Mistral LLM service.")
    
    def preprocess_image(self, image_path: str) -> np.ndarray:
        """
        Prétraite l'image pour améliorer la reconnaissance OCR
        
        :param image_path: Chemin de l'image
        :return: Image prétraitée
        """
        try:
            # Charger l'image
            image = cv2.imread(image_path)
            
            # Vérifier si l'image est chargée
            if image is None:
                raise ValueError(f"Impossible de charger l'image : {image_path}")
            
            # Redimensionner l'image pour améliorer la qualité (2x plus grande)
            height, width = image.shape[:2]
            image = cv2.resize(image, (width*2, height*2), interpolation=cv2.INTER_CUBIC)
            
            # Convertir en niveaux de gris
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Amélioration du contraste
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            
            # Réduction du bruit avec préservation des détails
            denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
            
            # Binarisation adaptative avec paramètres ajustés
            binary = cv2.adaptiveThreshold(
                denoised, 255, 
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 13, 8  # Ajusté pour améliorer la détection des textes fins
            )
            
            # Dilatation légère pour connecter les caractères fragmentés
            kernel = np.ones((1,1), np.uint8)
            dilated = cv2.dilate(binary, kernel, iterations=1)
            
            # Érosion pour restaurer la forme originale des caractères
            eroded = cv2.erode(dilated, kernel, iterations=1)
            
            # Inverser l'image pour obtenir le texte en noir sur fond blanc
            inverted = cv2.bitwise_not(eroded)
            
            # Sauvegarder l'image prétraitée pour le débogage (facultatif)
            debug_dir = 'preprocessed_images'
            os.makedirs(debug_dir, exist_ok=True)
            base_filename = os.path.basename(image_path)
            debug_path = os.path.join(debug_dir, f"{os.path.splitext(base_filename)[0]}_preprocessed.jpg")
            cv2.imwrite(debug_path, inverted)
            
            return inverted
            
        except Exception as e:
            self.logger.error(f"Erreur de prétraitement de l'image : {e}")
            raise
    
    def extract_text(self, image_path: str) -> str:
        """
        Extraction de texte avec Tesseract
        
        :param image_path: Chemin de l'image
        :return: Texte extrait
        """
        try:
            # Prétraitement de l'image
            preprocessed = self.preprocess_image(image_path)
            
            # S'assurer que la variable d'environnement est définie avant chaque appel
            tessdata_path = r'C:\Program Files\Tesseract-OCR\tessdata'
            os.environ['TESSDATA_PREFIX'] = tessdata_path
            
            # Configuration Tesseract détaillée pour les tickets de caisse
            # PSM 4 : Mode colonne unique pour mieux gérer les tickets
            custom_config = r'--oem 3 --psm 4 ' \
                        r'-c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz,.€/:- ' \
                        r'--dpi 300'
            
            # Extraction du texte
            text = pytesseract.image_to_string(
                preprocessed, 
                lang=self.lang, 
                config=custom_config
            )
            
            # Si aucun texte n'est extrait, essayez avec PSM 6 (bloc uniforme)
            if not text.strip():
                self.logger.warning(f"Aucun texte extrait avec PSM 4, essai avec PSM 6...")
                custom_config = r'--oem 3 --psm 6 ' \
                            r'-c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz,.€/:- ' \
                            r'--dpi 300'
                text = pytesseract.image_to_string(
                    preprocessed, 
                    lang=self.lang, 
                    config=custom_config
                )
            
            # Si toujours pas de texte, essayez PSM 3 (segmentation auto)
            if not text.strip():
                self.logger.warning(f"Aucun texte extrait avec PSM 6, essai avec PSM 3...")
                custom_config = r'--oem 3 --psm 3 ' \
                            r'-c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz,.€/:- ' \
                            r'--dpi 300'
                text = pytesseract.image_to_string(
                    preprocessed, 
                    lang=self.lang, 
                    config=custom_config
                )
                
            if not text:
                self.logger.warning(f"Aucun texte extrait de l'image {image_path}")
                
            # Sauvegarder le texte brut pour débogage
            debug_dir = 'ocr_results'
            os.makedirs(debug_dir, exist_ok=True)
            base_filename = os.path.basename(image_path)
            debug_path = os.path.join(debug_dir, f"{os.path.splitext(base_filename)[0]}_ocr.txt")
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(text)
                
            return self._clean_extracted_text(text)
            
        except Exception as e:
            self.logger.error(f"Erreur Tesseract : {e}")
            return ""
    
    def _clean_extracted_text(self, text: str) -> str:
        """
        Basic cleaning of OCR-extracted text.
        
        :param text: Raw OCR text
        :return: Cleaned text
        """
        if not text:
            return ""
            
        # Remove problematic characters
        cleaned = text.replace('\x0c', '')  # Page break character
        
        # Remove multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Remove empty lines
        cleaned = '\n'.join([line for line in cleaned.split('\n') if line.strip()])
        
        return cleaned
    
    def process_receipt(self, image_path: str) -> Dict[str, Any]:
        """
        Traitement complet d'un ticket de caisse
        
        :param image_path: Chemin de l'image
        :return: Dictionnaire avec le texte extrait et les données structurées
        """
        try:
            # Extraction du texte
            extracted_text = self.extract_text(image_path)
            
            if not extracted_text:
                self.logger.error(f"Échec de l'extraction de texte pour {image_path}")
                return {
                    "success": False,
                    "error": "Aucun texte extrait de l'image",
                    "extracted_text": "",
                    "validated_data": {"vendor": "Unknown", "date": "Unknown", "total": 0.0, "line_items": []}
                }
            
            # Nettoyage avec Mistral
            cleaned_text = self.clean_text_with_mistral(extracted_text)
            
            # Classification avec Mistral
            classified_data = self.classify_data_with_mistral(cleaned_text)
            
            return {
                "success": True,
                "extracted_text": cleaned_text,
                "validated_data": classified_data
            }
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du ticket : {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "validated_data": {"vendor": "Unknown", "date": "Unknown", "total": 0.0, "line_items": []}
            }
    
    def clean_text_with_mistral(self, raw_text: str) -> str:
        """Clean OCR text using Mistral and calculate missing values"""
        # Skip processing if the text is very short
        if not raw_text or len(raw_text.strip()) < 10:
            self.logger.warning("Text too short to clean, returning original")
            return raw_text
            
        clean_prompt = f"""You are an expert receipt OCR cleaner and calculator. Carefully clean this OCR text from a receipt:

```
{raw_text}
```

Clean the text by:
1. Fixing character recognition errors (e.g., '0rangina' → 'Orangina')
2. Removing irrelevant text not from the receipt
3. Preserving numerical values, prices, dates, and product names exactly
4. Maintaining original language and layout structure

IMPORTANT: Perform calculations for any missing values based on existing data:
- If an item has quantity and price but no total, calculate the item total (quantity × price)
- If the receipt shows tax rate (e.g., "TVA 20%") and base amount but no tax amount, calculate the tax amount
- If the receipt has subtotal and tax but no final total, calculate the final total (subtotal + tax)
- If the receipt shows multiple items but no subtotal, calculate the subtotal by summing item totals

Only add calculated values if they're missing and you have enough information to calculate them accurately.
DO NOT add any text that isn't in or directly calculable from the receipt.
DO NOT invent any information.

Return ONLY the cleaned and numerically corrected text.
"""
        
        cleaned = self.llm_service.generate(
            prompt=clean_prompt,
            max_tokens=3000,
            temperature=0.1
        )
        
        # If we got back empty result or only whitespace
        if not cleaned or cleaned.isspace():
            self.logger.warning("Mistral returned empty cleaning result, using original text")
            return raw_text
            
        return cleaned
    
    def classify_data_with_mistral(self, cleaned_text: str) -> Dict[str, Any]:
        """Extract structured data from receipt text"""
        # Handle empty cleaned_text case
        if not cleaned_text or cleaned_text.strip() == "":
            self.logger.warning("Empty cleaned text received, using original text")
            return {"vendor": "Unknown", "date": "Unknown", "total": 0.0, "line_items": []}
            
        # Example receipt
        example_text = """
Carrefour Market
25 Avenue des Champs-Élysées
75008 Paris
Tel: +33 1 42 25 12 35
www.carrefour.fr
SIRET: 552 081 317 00595
TVA Intracom: FR95 552081317
Capital: 5,596,520,000 €
NAF: 4711F

25/10/2023 14:30
Receipt #2568791
Caissier: Jean Dupont
Client: Particulier

Coca-Cola 330ml      2x1.50     3.00
Evian Water 1L       1x2.10     2.10
Baguette             2x1.20     2.40
Camembert            1x4.50     4.50
Oranges 1kg          1x3.20     3.20
Chicken Breast       0.5x12.40  6.20
                     ---------
SUBTOTAL:            21.40
TVA (20%):            4.28
TOTAL TTC:           25.68

CARD PAYMENT: VISA **** 4217
AUTHORIZED

Thank you for shopping at Carrefour!
        """
        
        example_output = """
{
  "vendor": "Carrefour Market",
  "date": "2023-10-25",
  "total": 25.68,
  "payment_method": "Card",
  "category": "Grocery",
  "store_address": "25 Avenue des Champs-Élysées, 75008 Paris",
  "store_phone": "+33 1 42 25 12 35",
  "store_email": "",
  "store_website": "www.carrefour.fr",
  "tax": 4.28,
  "subtotal": 21.40,
  "siret": "552 081 317 00595",
  "tva_number": "FR95 552081317",
  "capital": "5,596,520,000 €",
  "naf_code": "4711F",
  "cashier": "Jean Dupont",
  "client_type": "Particulier",
  "line_items": [
    {
      "description": "Coca-Cola 330ml",
      "quantity": 2,
      "price": 1.50
    },
    {
      "description": "Evian Water 1L",
      "quantity": 1,
      "price": 2.10
    },
    {
      "description": "Baguette",
      "quantity": 2,
      "price": 1.20
    },
    {
      "description": "Camembert",
      "quantity": 1,
      "price": 4.50
    },
    {
      "description": "Oranges 1kg",
      "quantity": 1,
      "price": 3.20
    },
    {
      "description": "Chicken Breast",
      "quantity": 0.5,
      "price": 12.40
    }
  ]
}
        """
        
        # Enhanced prompt with explicit test example
        classification_prompt = f"""You are an expert receipt parser. Extract structured data from this receipt:

RECEIPT TEXT:
```
{cleaned_text}
```

IMPORTANT: Verify that the sum of all line items equals the total amount on the receipt.
If there's a discrepancy:
1. Check if any line items have incorrect prices or quantities
2. Adjust quantities or prices if you can confidently determine the correct values
3. Make sure the line_items array accurately reflects what's on the receipt
4. The final calculated total should match the total displayed on the receipt

EXAMPLE CORRECT OUTPUT:
```
{example_output}
```

Extract EXACTLY these fields in valid JSON format:
- vendor: Store name (e.g. "Carrefour")
- date: Format as YYYY-MM-DD 
- total: Total amount as number
- payment_method: How the customer paid (e.g. "Cash", "Card", "Credit Card", "Check")
- category: Type of store/purchase (e.g. "Grocery", "Restaurant", "Retail", "Pharmacy")
- store_address: Complete store address if available
- store_phone: Phone number if available
- store_email: Email if available
- store_website: Website if available
- tax: Tax amount if specified
- subtotal: Subtotal before tax if specified
- siret: French business identification number if present (e.g. "552 081 317 00595")
- tva_number: TVA/VAT number if present (e.g. "FR95 552081317")
- capital: Company capital amount if present
- naf_code: French business activity code if present
- cashier: Name of the cashier if present
- client_type: Type of customer if specified (e.g. "Particulier", "Professionnel")
- line_items: Array of items with description, quantity and price

Extract ONLY what's in the receipt. If you can't determine a value, use "Unknown" for text fields, 0 for numbers.
Return ONLY the JSON data with no additional text or explanation.
"""
        
        self.logger.info(f"Sending classification prompt to Mistral")
        response = self.llm_service.generate(classification_prompt, temperature=0.0)
        
        if not response or response.isspace():
            self.logger.error("Empty response from Mistral API")
            return {"vendor": "Unknown", "date": "Unknown", "total": 0.0, "line_items": []}
        
        result = self._parse_mistral_response(response)
        self.logger.info(f"Classified result: {json.dumps(result, indent=2)}")
        return result

    def _parse_mistral_response(self, response: str) -> Dict[str, Any]:
        """Handle Mistral's JSON response format with improved error handling"""
        try:
            # Try to extract just the JSON part in case there's surrounding text
            json_match = re.search(r'({[\s\S]*})', response)
            if json_match:
                response = json_match.group(1)
                
            # Parse the JSON data
            data = json.loads(response)
            
            # Validate structure
            if not isinstance(data, dict):
                raise ValueError("Response is not a dictionary")
                
            # Ensure required fields exist
            default_data = {
                "vendor": "Unknown", 
                "date": "Unknown", 
                "total": 0.0,
                "payment_method": "Unknown",
                "category": "Uncategorized",
                "store_address": "",
                "store_phone": "",
                "store_email": "",
                "store_website": "",
                "tax": 0.0,
                "subtotal": 0.0,
                "siret": "",
                "tva_number": "",
                "capital": "",
                "naf_code": "",
                "cashier": "",
                "client_type": "",
                "line_items": []
            }
            
            # Update default_data with any valid fields from the response
            for key in default_data:
                if key in data:
                    default_data[key] = data[key]
                    
            return default_data
            
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Failed to parse Mistral response: {str(e)}")
            self.logger.debug(f"Raw response: {response[:500]}")
            return {"vendor": "Unknown", "date": "Unknown", "total": 0.0, "line_items": []}

# Import pour le test principal
def main():
    """
    Point d'entrée pour le test du processeur
    """
    # Initialiser le processeur
    processor = SimplifiedReceiptProcessor()
    
    # Répertoire des tickets de test
    input_directory = 'input_tickets'
    
    # Vérifier si le répertoire existe
    if not os.path.exists(input_directory):
        os.makedirs(input_directory)
        print(f"Dossier {input_directory} créé. Veuillez y placer vos tickets de caisse.")
    
    # Liste des fichiers image
    image_files = [f for f in os.listdir(input_directory) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    # Traitement de chaque ticket
    if not image_files:
        print("Aucun ticket trouvé. Veuillez ajouter des images dans le dossier input_tickets.")
    
    for filename in image_files:
        try:
            # Chemin complet de l'image
            image_path = os.path.join(input_directory, filename)
            
            # Traitement du ticket
            print(f"\n--- Traitement du ticket : {filename} ---")
            result = processor.process_receipt(image_path)
            
            # Affichage des résultats
            print("\nTexte extrait :")
            print(result['extracted_text'])
            
            print("\nMontants extraits :")
            print(json.dumps(result['validated_data'], indent=2, ensure_ascii=False))
        
        except Exception as e:
            print(f"Erreur lors du traitement de {filename} : {e}")

if __name__ == '__main__':
    main()