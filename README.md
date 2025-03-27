# Receipt OCR and Loyalty App with GCP Storage

This application processes receipts using OCR, extracts useful information, and integrates with a loyalty program, storing all data in Google Cloud Storage.

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Google Cloud Storage

1. Create a GCP project (if you don't have one)
2. Create a new storage bucket named `hackathon-ocr-2025-group1-bucket`
3. Create a service account with Storage Admin permissions
4. Download the service account JSON key file
5. Rename it to `hackathon-ocr-2025-group1-client.json` and place it in the app directory
6. Update the `.env` file with your bucket name and credentials path

### 3. Configure Environment Variables

Copy the `.env.example` file to `.env` and update the values:

```bash
cp .env.example .env
```

Update the following variables:
- `SECRET_KEY`: Set a secure random string for Flask sessions
- `GCP_BUCKET_NAME`: Your GCP bucket name
- `GCP_CREDENTIALS_PATH`: Path to your service account key file
- Other API keys as needed

## Features

### GCP Storage Integration

The application uses Google Cloud Storage as a NoSQL database alternative, storing:
- Receipt JSON data in the `receipts/json/` folder
- Receipt CSV data in the `receipts/csv/` folder 
- Receipt images in the `receipts/images/` folder

### Benefits of GCP Storage

- **Scalability**: Handles large volumes of receipts and images without local storage constraints
- **Durability**: Data is automatically replicated and protected
- **Global Accessibility**: Access receipts from anywhere
- **Security**: Fine-grained access control
- **Cost-effective**: Pay only for what you use
- **Integration**: Easy integration with other GCP services

## Usage

1. Start the Flask application:

```bash
python app.py
```

2. Access the web interface at http://localhost:5000
3. Upload receipts to process them and store in GCP Storage
4. View receipt history and details, with images served directly from GCP Storage

## API Endpoints

- `/`: Home page
- `/upload`: Receipt upload endpoint (POST)
- `/receipt/<receipt_id>`: View receipt details
- `/history`: View all receipts (admin mode)
- `/my-receipts`: View user's receipts (when logged in)
- `/login`: User login
- `/profile`: User profile
- `/data/images/<filename>`: Redirects to GCP Storage image URLs

## Storage Structure

```
receipts/
├── json/
│   ├── receipt_20250101_123456.json
│   └── ...
├── csv/
│   ├── receipt_20250101_123456.csv
│   └── ...
└── images/
    ├── receipt_20250101_123456.jpg
    └── ...
```

## Overview
This application provides advanced receipt processing capabilities using OCR (Optical Character Recognition) and AI analysis. It combines traditional OCR with the power of Large Language Models to extract, clean, and structure data from receipt images.

## Features
- **Dual OCR Processing**: Uses Veryfi API for professional OCR with fallback to Tesseract OCR
- **AI-Powered Text Cleaning**: Employs Mistral LLM to clean and normalize OCR text
- **Intelligent Data Extraction**: Extracts structured data including vendor, date, total amount, and line items
- **Total Verification**: Automatically verifies that line items add up to the total and makes corrections if needed
- **Web Interface**: User-friendly Flask web application for uploading and viewing receipts
- **Comprehensive Storage**: Stores original images, raw OCR text, and structured data

## Dependencies
- Python 3.8+
- Flask
- OpenCV
- Pytesseract
- Veryfi Client
- NumPy
- Pandas
- Requests
- Python-dotenv

## Installation
1. Clone the repository
2. Install Tesseract OCR (Windows: https://github.com/UB-Mannheim/tesseract/wiki)
3. Install required Python packages:
   ```
   pip install -r requirements.txt
   ```
4. Create a `.env` file with the following variables:
   ```
   VERYFI_CLIENT_ID=your_veryfi_client_id
   VERYFI_CLIENT_SECRET=your_veryfi_client_secret
   VERYFI_USERNAME=your_veryfi_username
   VERYFI_API_KEY=your_veryfi_api_key
   MISTRAL_API_KEY=your_mistral_api_key
   MISTRAL_API_ENDPOINT=https://api.mistral.ai/v1/chat/completions
   ```

## Usage
1. Start the Flask application:
   ```
   python app.py
   ```
2. Access the web interface at `http://localhost:5000` or the IP shown in the console
3. Upload a receipt image
4. View the extracted and processed data

## Components
- **receipt_utils.py**: Handles Veryfi API integration and base receipt processing
- **mistral_llm_service.py**: Manages communication with the Mistral API
- **advanced_receipt_ocr.py**: Implements OCR with Tesseract and AI-powered analysis
- **app.py**: Flask web application for user interaction

## Workflow
1. Image is uploaded through the web interface
2. Primary OCR processing with Veryfi API (with fallback to Tesseract)
3. Text cleaning with Mistral LLM
4. Structured data extraction with intelligent verification
5. Results storage and display

## Notes
- The application requires internet access for API communication
- For testing without APIs, set `MOCK_API=True` in your environment variables
- The application creates directories for data storage if they don't exist 



receipt-ocr-analysis/
│
├── new_app/
│ ├── advanced_receipt_ocr.py
│ ├── app.py
│ ├── mistral_llm_service.py
│ ├── receipt_utils.py
│ ├── requirements.txt
│ └── README.md
│
├── input_tickets/ # Directory for input receipt images
├── ocr_results/ # Directory for storing OCR results
├── preprocessed_images/ # Directory for storing preprocessed images
└── .env # Environment variables for API keys