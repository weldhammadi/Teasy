#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script d'importation des tickets dans la base de données de fidélité
Ce script prend un fichier JSON de ticket et l'importe dans la base de données SQLite
"""

import json
import os
import sys
import traceback
from datetime import datetime

# Importer l'intégrateur de base de données
from db_integrator import DatabaseIntegrator

# Configuration des chemins
# Chemin vers la base de données SQLite
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fidelity_db.sqlite')
# Dossier contenant les fichiers JSON des tickets
JSON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'json')
# Dossier contenant les images des tickets
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'images')

def find_receipt_files():
    """Trouve tous les fichiers de tickets disponibles"""
    if not os.path.exists(JSON_DIR):
        print(f"Erreur: Le dossier JSON n'existe pas: {JSON_DIR}")
        return []
    
    json_files = [f for f in os.listdir(JSON_DIR) if f.endswith('.json')]
    if not json_files:
        print(f"Aucun fichier JSON trouvé dans {JSON_DIR}")
        return []
    
    receipts = []
    for json_file in json_files:
        json_path = os.path.join(JSON_DIR, json_file)
        image_file = json_file.replace('.json', '.jpg')
        image_path = os.path.join(IMAGES_DIR, image_file)
        
        # Vérifier si l'image existe
        if not os.path.exists(image_path):
            image_path = None
        
        receipts.append({
            'json_path': json_path,
            'image_path': image_path,
            'filename': json_file
        })
    
    return receipts

def preprocess_receipt_data(data):
    """Prétraitement des données du ticket pour s'assurer qu'elles sont dans le bon format"""
    # Copier les données pour éviter de modifier l'original
    processed_data = data.copy()
    
    # Traiter line_items
    if 'line_items' in processed_data:
        # Si line_items est une chaîne, essayer de la décoder
        if isinstance(processed_data['line_items'], str):
            try:
                processed_data['line_items'] = json.loads(processed_data['line_items'])
            except json.JSONDecodeError:
                processed_data['line_items'] = []
        
        # S'assurer que line_items est une liste
        if not isinstance(processed_data['line_items'], list):
            processed_data['line_items'] = []
        
        # Vérifier chaque élément de line_items
        for i, item in enumerate(processed_data['line_items']):
            if not isinstance(item, dict):
                processed_data['line_items'][i] = {
                    'description': str(item),
                    'quantity': 1,
                    'price': 0
                }
            else:
                # S'assurer que les champs numériques sont des nombres
                for key in ['quantity', 'price']:
                    if key in item and not isinstance(item[key], (int, float)):
                        try:
                            item[key] = float(item[key])
                        except (ValueError, TypeError):
                            item[key] = 1 if key == 'quantity' else 0
    else:
        processed_data['line_items'] = []
    
    # Traiter veryfi_data
    if 'veryfi_data' in processed_data:
        if isinstance(processed_data['veryfi_data'], str):
            try:
                processed_data['veryfi_data'] = json.loads(processed_data['veryfi_data'])
            except json.JSONDecodeError:
                processed_data['veryfi_data'] = {}
    
    # S'assurer que les champs numériques sont des nombres
    for key in ['total', 'tax', 'subtotal']:
        if key in processed_data:
            if not isinstance(processed_data[key], (int, float)):
                try:
                    processed_data[key] = float(processed_data[key])
                except (ValueError, TypeError):
                    processed_data[key] = 0.0
                    
    # S'assurer que la date est au bon format
    if 'date' in processed_data and processed_data['date']:
        # Essayer différents formats de date si nécessaire
        if not isinstance(processed_data['date'], str):
            processed_data['date'] = str(processed_data['date'])
    
    return processed_data

def import_receipt(receipt_info):
    """Importe un ticket dans la base de données"""
    print(f"\nTraitement du ticket: {receipt_info['filename']}")
    
    # Charger les données du ticket
    try:
        with open(receipt_info['json_path'], 'r', encoding='utf-8') as f:
            receipt_data = json.load(f)
        
        # Prétraiter les données
        processed_data = preprocess_receipt_data(receipt_data)
        
        # Afficher les informations principales
        print(f"Magasin: {processed_data.get('vendor', 'Inconnu')}")
        print(f"Date: {processed_data.get('date', 'Inconnue')}")
        print(f"Montant: {processed_data.get('total', 0)}")
        print(f"Nombre d'articles: {len(processed_data.get('line_items', []))}")
        
        # Chemin de l'image
        image_path = receipt_info['image_path'] if receipt_info['image_path'] else "NoImage"
        
        # Intégrer dans la base de données
        db_integrator = DatabaseIntegrator(DB_PATH)
        success, transaction_id, message = db_integrator.process_receipt_data(processed_data, image_path)
        
        if success:
            print(f"✓ Importation réussie! Transaction ID: {transaction_id}")
            return True, transaction_id
        else:
            print(f"✗ Échec de l'importation: {message}")
            return False, None
    
    except Exception as e:
        print(f"✗ Erreur lors du traitement du ticket: {str(e)}")
        traceback.print_exc()
        return False, None

def main():
    """Fonction principale"""
    print("=" * 60)
    print("Import de tickets vers la base de données de fidélité")
    print("=" * 60)
    
    # Vérifier que la base de données existe
    if not os.path.exists(DB_PATH):
        print(f"Erreur: La base de données n'existe pas: {DB_PATH}")
        print("Veuillez créer la base de données avec les tables requises d'abord.")
        return
    
    # Trouver les fichiers de tickets
    receipts = find_receipt_files()
    if not receipts:
        print("Aucun ticket trouvé pour importation.")
        return
    
    print(f"Trouvé {len(receipts)} tickets à importer.")
    
    # Demander confirmation
    if len(receipts) > 1:
        confirm = input(f"Voulez-vous importer tous les {len(receipts)} tickets? (o/n): ")
        if confirm.lower() != 'o':
            selected = int(input(f"Entrez le numéro du ticket à importer (1-{len(receipts)}): "))
            if 1 <= selected <= len(receipts):
                receipts = [receipts[selected-1]]
            else:
                print("Sélection invalide. Annulation.")
                return
    
    # Importer chaque ticket
    success_count = 0
    for receipt in receipts:
        success, _ = import_receipt(receipt)
        if success:
            success_count += 1
    
    # Résumé
    print("\n" + "=" * 60)
    print(f"Importation terminée: {success_count}/{len(receipts)} tickets importés avec succès.")
    print("=" * 60)

if __name__ == "__main__":
    main()