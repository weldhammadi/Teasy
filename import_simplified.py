#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script d'importation simplifié pour les tickets
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime
import random

# Configuration
DB_PATH = "fidelity_db.sqlite"  # Chemin vers votre base de données
JSON_DIR = "data/json"         # Dossier contenant les fichiers JSON
IMAGES_DIR = "data/images"     # Dossier contenant les images

def import_ticket(json_path):
    """Importe un ticket dans la base de données"""
    print(f"\nTraitement du ticket: {os.path.basename(json_path)}")
    
    # Charger les données du ticket
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extraire les informations principales
    vendor = data.get('vendor', 'Inconnu')
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    total = float(data.get('total', 0))
    
    print(f"Magasin: {vendor}")
    print(f"Date: {date}")
    print(f"Montant: {total}")
    
    # Chemin de l'image
    image_name = os.path.basename(json_path).replace('.json', '.jpg')
    image_path = os.path.join(IMAGES_DIR, image_name)
    if not os.path.exists(image_path):
        image_path = "pas_d_image.jpg"
    
    # Connexion à la base de données
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Désactiver temporairement les contraintes de clés étrangères pour simplifier
        cursor.execute("PRAGMA foreign_keys = OFF")
        
        # 1. Créer un client fictif
        client_uuid = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO clients (uuid, nom, prenom, statut, segment)
        VALUES (?, ?, ?, ?, ?)
        """, (client_uuid, "Client Test", "Prénom Test", "actif", "standard"))
        client_id = cursor.lastrowid
        
        # 2. Créer une carte de fidélité (en omettant niveau_fidelite pour utiliser la valeur par défaut)
        card_number = f"CARD-{random.randint(10000, 99999)}"
        cursor.execute("""
        INSERT INTO cartes_fidelite (client_id, numero_carte, statut)
        VALUES (?, ?, ?)
        """, (client_id, card_number, "active"))
        card_id = cursor.lastrowid
        
        # 3. Créer un magasin
        cursor.execute("""
        INSERT INTO points_vente (nom, type, statut)
        VALUES (?, ?, ?)
        """, (vendor, "franchise", "actif"))
        store_id = cursor.lastrowid
        
        # 4. Créer une transaction
        cursor.execute("""
        INSERT INTO transactions (client_id, carte_id, magasin_id, date_transaction, montant_total, type_paiement)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (client_id, card_id, store_id, date, total, "cb"))
        transaction_id = cursor.lastrowid
        
        # 5. Créer une catégorie de produit simple
        cursor.execute("""
        INSERT INTO categories_produits (nom, description)
        VALUES (?, ?)
        """, ("Divers", "Catégorie générique"))
        category_id = cursor.lastrowid
        
        # 6. Créer un produit générique
        cursor.execute("""
        INSERT INTO produits (reference, nom, description, categorie_id, prix_standard)
        VALUES (?, ?, ?, ?, ?)
        """, (f"PROD-{random.randint(10000, 99999)}", f"Achat {vendor}", "Produit générique", category_id, total))
        product_id = cursor.lastrowid
        
        # 7. Créer un détail de transaction
        cursor.execute("""
        INSERT INTO details_transactions (transaction_id, produit_id, quantite, prix_unitaire, montant_ligne)
        VALUES (?, ?, ?, ?, ?)
        """, (transaction_id, product_id, 1, total, total))
        
        # 8. Enregistrer le ticket
        cursor.execute("""
        INSERT INTO tickets_caisse (client_id, transaction_id, date_upload, date_transaction, 
                                   magasin_id, montant_total, image_path, ticket_hash, 
                                   statut_traitement, validation_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (client_id, transaction_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
              date, store_id, total, image_path, str(uuid.uuid4()), 
              "traité", "validated"))
        
        # Valider les changements
        conn.commit()
        print(f"✓ Importation réussie! Transaction ID: {transaction_id}")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Erreur: {str(e)}")
        return False
        
    finally:
        conn.close()

def main():
    """Fonction principale"""
    print("=" * 60)
    print("Import simplifié de tickets vers la base de données")
    print("=" * 60)
    
    # Vérifier si le répertoire existe
    if not os.path.exists(JSON_DIR):
        print(f"Erreur: Le répertoire {JSON_DIR} n'existe pas.")
        return
    
    # Lister tous les fichiers JSON
    json_files = [f for f in os.listdir(JSON_DIR) if f.endswith('.json')]
    if not json_files:
        print(f"Aucun fichier JSON trouvé dans {JSON_DIR}")
        return
    
    print(f"Trouvé {len(json_files)} tickets à importer.")
    
    # Demander confirmation
    confirm = input(f"Voulez-vous importer tous les {len(json_files)} tickets? (o/n): ")
    if confirm.lower() != 'o':
        print("Importation annulée.")
        return
    
    # Importer chaque ticket
    success_count = 0
    for json_file in json_files:
        json_path = os.path.join(JSON_DIR, json_file)
        if import_ticket(json_path):
            success_count += 1
    
    print("\n" + "=" * 60)
    print(f"Importation terminée: {success_count}/{len(json_files)} tickets importés avec succès.")
    print("=" * 60)

if __name__ == "__main__":
    main()