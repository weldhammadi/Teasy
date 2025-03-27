#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script d'importation minimal pour les tickets
"""

import json
import os
import sqlite3
import datetime
import random
import traceback

# Configuration
DB_PATH = "fidelity.sqlite"  # Chemin vers la base de données
JSON_DIR = "data/json"         # Dossier des JSON

def create_database():
    """Crée une base de données simple avec une seule table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        vendor TEXT,
        date TEXT,
        total REAL,
        raw_data TEXT,
        import_date TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    print("Base de données préparée.")

def import_receipt(json_path):
    """Importe un ticket de manière minimale"""
    filename = os.path.basename(json_path)
    print(f"\nTraitement de: {filename}")
    
    try:
        # Charger le JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extraire les données essentielles
        vendor = "Inconnu"
        if "vendor" in data:
            v = data["vendor"]
            if isinstance(v, dict) and "name" in v:
                vendor = v["name"]
            elif isinstance(v, str):
                vendor = v
        
        # Gérer la date
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        if "date" in data and data["date"]:
            date = str(data["date"])
        
        # Gérer le total
        total = 0.0
        if "total" in data and data["total"] is not None:
            try:
                total = float(data["total"])
            except (ValueError, TypeError):
                total = 0.0
        
        print(f"Vendeur: {vendor}")
        print(f"Date: {date}")
        print(f"Total: {total}")
        
        # Sérialiser les données complètes
        raw_data = json.dumps(data)
        
        # Enregistrer dans la base de données
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
        INSERT INTO receipts (filename, vendor, date, total, raw_data, import_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            filename,
            vendor,
            date,
            total,
            raw_data,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        
        conn.commit()
        conn.close()
        
        print("✓ Importation réussie!")
        return True
    
    except Exception as e:
        print(f"✗ Erreur: {str(e)}")
        traceback.print_exc()
        return False

def main():
    """Fonction principale"""
    print("=" * 60)
    print("IMPORTATION MINIMALE DE TICKETS")
    print("=" * 60)
    
    # Créer la base de données
    create_database()
    
    # Vérifier le dossier JSON
    if not os.path.exists(JSON_DIR):
        print(f"Erreur: Le dossier {JSON_DIR} n'existe pas.")
        return
    
    # Lister les fichiers
    json_files = [f for f in os.listdir(JSON_DIR) if f.endswith('.json')]
    if not json_files:
        print("Aucun fichier JSON trouvé.")
        return
    
    print(f"Trouvé {len(json_files)} fichiers à importer.")
    
    # Importer chaque fichier
    success = 0
    for json_file in json_files:
        json_path = os.path.join(JSON_DIR, json_file)
        if import_receipt(json_path):
            success += 1
    
    print("\n" + "=" * 60)
    print(f"Importation terminée: {success}/{len(json_files)} réussis")
    print("=" * 60)

if __name__ == "__main__":
    main()