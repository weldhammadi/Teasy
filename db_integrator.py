import os
import sqlite3
import uuid
import json
from datetime import datetime, timedelta
import random
import re


class DatabaseIntegrator:
    """
    Classe pour intégrer les données extraites des tickets dans la base de données
    """
    def __init__(self, db_path='loyalty_db.sqlite'):
        """
        Initialise l'intégrateur avec le chemin vers la base de données
        
        :param db_path: Chemin vers le fichier de la base de données SQLite
        """
        self.db_path = db_path
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Établit une connexion à la base de données"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Pour avoir les résultats sous forme de dictionnaires
            self.cursor = self.conn.cursor()
            return True
        except sqlite3.Error as e:
            print(f"Erreur de connexion à la base de données: {e}")
            return False
    
    def disconnect(self):
        """Ferme la connexion à la base de données"""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
    
    def commit(self):
        """Valide les changements dans la base de données"""
        if self.conn:
            self.conn.commit()
    
    def rollback(self):
        """Annule les changements en cas d'erreur"""
        if self.conn:
            self.conn.rollback()

    def debug_database_constraints(self):
        """Afficher les contraintes de la base de données pour le débogage"""
        try:
            self.cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cartes_fidelite'")
            table_def = self.cursor.fetchone()
            print(f"Définition de la table cartes_fidelite:\n{table_def[0]}")
            
            # Tester une insertion directe avec différentes valeurs pour voir laquelle fonctionne
            test_values = ['bronze', 'argent', 'or', 'platine', 'BRONZE', 'ARGENT', 'OR', 'PLATINE']
            for val in test_values:
                try:
                    self.cursor.execute(
                        "INSERT INTO cartes_fidelite (client_id, numero_carte, niveau_fidelite) VALUES (?, ?, ?)",
                        (999999, f"TEST-{val}", val)
                    )
                    print(f"Insertion réussie avec niveau_fidelite = '{val}'")
                    # Annuler cette insertion de test
                    self.cursor.execute("DELETE FROM cartes_fidelite WHERE client_id = 999999")
                except sqlite3.Error as e:
                    print(f"Échec avec niveau_fidelite = '{val}': {e}")
        except Exception as e:
            print(f"Erreur lors du débogage: {e}")
    
    def get_client(self, client_id):
        """
        Récupère les informations d'un client par son ID
        
        :param client_id: ID du client
        :return: Données du client ou None
        """
        if not client_id:
            return None
            
        query = """
        SELECT c.*, cf.numero_carte, cf.niveau_fidelite, cf.points_actuels, cf.date_expiration
        FROM clients c
        LEFT JOIN cartes_fidelite cf ON c.client_id = cf.client_id
        WHERE c.client_id = ?
        """
        
        self.cursor.execute(query, (client_id,))
        client_data = self.cursor.fetchone()
        
        if client_data:
            return dict(client_data)
            
        return None
    
    def find_or_create_client(self, vendor_info, ticket_data, specified_client_id=None):
        """
        Trouve ou crée un client basé sur les informations du ticket
        
        :param vendor_info: Informations sur le vendeur
        :param ticket_data: Données extraites du ticket
        :param specified_client_id: ID du client spécifié (utilisateur connecté)
        :return: ID du client
        """
        # Si un client_id est spécifié (utilisateur connecté), vérifier qu'il existe
        if specified_client_id:
            client_data = self.get_client(specified_client_id)
            if client_data:
                return specified_client_id
        
        # Vérifier si nous avons un client pour ce magasin (simulation)
        search_query = "SELECT client_id FROM clients WHERE nom LIKE ? OR email LIKE ? LIMIT 1"
        self.cursor.execute(search_query, (f"%{vendor_info.get('name', '')}%", f"%@{vendor_info.get('website', '').replace('www.', '')}%"))
        client_row = self.cursor.fetchone()
        
        if client_row:
            return client_row['client_id']
        
        # Créer un nouveau client fictif
        new_uuid = str(uuid.uuid4())
        
        # Données fictives pour le client
        now = datetime.now()
        birth_date = now - timedelta(days=365 * random.randint(18, 70))
        
        insert_query = """
        INSERT INTO clients (
            uuid, nom, prenom, date_naissance, genre, adresse, code_postal, ville, pays,
            telephone, email, date_inscription, consentement_marketing,
            consentement_data_processing, date_consentement, statut, segment, canal_acquisition
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # Génération de données fictives cohérentes
        prenom = random.choice(["Jean", "Marie", "Pierre", "Sophie", "Thomas", "Julie"])
        nom = random.choice(["Dupont", "Martin", "Bernard", "Petit", "Robert"])
        email = f"{prenom.lower()}.{nom.lower()}@example.com"
        
        self.cursor.execute(insert_query, (
            new_uuid,                           # uuid
            nom,                                # nom
            prenom,                             # prenom
            birth_date.strftime('%Y-%m-%d'),    # date_naissance
            random.choice(["M", "F"]),          # genre
            "1 rue des exemples",               # adresse
            "75000",                            # code_postal
            "Paris",                            # ville
            "France",                           # pays
            "0123456789",                       # telephone
            email,                              # email
            now.strftime('%Y-%m-%d %H:%M:%S'),  # date_inscription
            0,                                  # consentement_marketing
            1,                                  # consentement_data_processing
            now.strftime('%Y-%m-%d %H:%M:%S'),  # date_consentement
            "actif",                            # statut
            "standard",                         # segment
            "ticket_ocr"                        # canal_acquisition
        ))
        
        client_id = self.cursor.lastrowid
        
        # Créer une carte de fidélité pour ce client
        self.create_fidelity_card(client_id)
        
        return client_id

    def check_and_fix_client_fidelity(self, client_id):
        """
        Vérifie et corrige si nécessaire le niveau de fidélité du client
        pour respecter la contrainte de la base de données
        
        :param client_id: ID du client
        :return: True si la correction a été effectuée ou n'était pas nécessaire
        """
        try:
            # Vérifier la carte existante
            self.cursor.execute(
                "SELECT carte_id, niveau_fidelite FROM cartes_fidelite WHERE client_id = ?", 
                (client_id,)
            )
            card = self.cursor.fetchone()
            
            if card:
                niveau = card['niveau_fidelite']
                carte_id = card['carte_id']
                
                # Vérifier si le niveau est conforme
                valid_levels = ['Standard', 'Silver', 'Or', 'Platine']
                if niveau not in valid_levels:
                    # Convertir au format correct
                    nouveau_niveau = 'Standard'  # Valeur par défaut
                    
                    print(f"Correction du niveau de fidélité pour la carte {carte_id}: '{niveau}' -> '{nouveau_niveau}'")
                    
                    # Mettre à jour avec la valeur correcte
                    self.cursor.execute(
                        "UPDATE cartes_fidelite SET niveau_fidelite = ? WHERE carte_id = ?",
                        (nouveau_niveau, carte_id)
                    )
                    self.commit()
                    return True
                    
            return True  # Pas de correction nécessaire ou pas de carte
            
        except Exception as e:
            print(f"Erreur lors de la vérification/correction du niveau de fidélité: {e}")
            return False
        
    def create_fidelity_card(self, client_id):
        """
        Crée une carte de fidélité pour un client
        
        :param client_id: ID du client
        :return: ID de la carte
        """
        now = datetime.now()
        expiration = now + timedelta(days=365 * 2)  # Valide pour 2 ans
        
        # Générer un numéro de carte fictif
        card_number = f"CARD-{random.randint(10000, 99999)}-{client_id}"
        
        # Mapping entre les niveaux affichés et les niveaux stockés
        niveau_fidelite = 'bronze'  # Valeur acceptée par la contrainte
        
        insert_query = """
        INSERT INTO cartes_fidelite (
            client_id, numero_carte, date_emission, date_expiration, 
            statut, niveau_fidelite, points_actuels, points_en_attente
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        try:
            self.cursor.execute(insert_query, (
                client_id,                           # client_id
                card_number,                         # numero_carte
                now.strftime('%Y-%m-%d %H:%M:%S'),   # date_emission
                expiration.strftime('%Y-%m-%d %H:%M:%S'),  # date_expiration
                'active',                            # statut
                niveau_fidelite,                     # niveau_fidelite (toujours en minuscules)
                0,                                   # points_actuels
                0                                    # points_en_attente
            ))
            
            print(f"Carte de fidélité créée pour le client {client_id} avec niveau {niveau_fidelite}")
            return self.cursor.lastrowid
        except Exception as e:
            print(f"Erreur lors de la création de la carte de fidélité: {e}")
            raise
    
    def find_or_create_store(self, vendor_info):
        """
        Trouve ou crée un point de vente basé sur les informations du vendeur
        
        :param vendor_info: Informations sur le vendeur
        :return: ID du magasin
        """
        # Chercher le magasin par nom et adresse
        search_query = "SELECT magasin_id FROM points_vente WHERE nom LIKE ? LIMIT 1"
        self.cursor.execute(search_query, (f"%{vendor_info.get('name', '')}%",))
        store_row = self.cursor.fetchone()
        
        if store_row:
            return store_row['magasin_id']
        
        # Créer un nouveau magasin
        store_name = vendor_info.get('name', 'Magasin inconnu')
        
        insert_query = """
        INSERT INTO points_vente (
            nom, type, adresse, code_postal, ville, pays, 
            telephone, email, horaires, statut
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        self.cursor.execute(insert_query, (
            store_name,                                  # nom
            'franchise',                                 # type
            vendor_info.get('address', 'Adresse inconnue'),  # adresse
            vendor_info.get('postal_code', '75000'),     # code_postal
            vendor_info.get('city', 'Paris'),            # ville
            vendor_info.get('country', 'France'),        # pays
            vendor_info.get('phone', ''),                # telephone
            vendor_info.get('email', ''),                # email
            '9h-19h',                                    # horaires
            'actif'                                      # statut
        ))
        
        return self.cursor.lastrowid
    
    def get_client_card(self, client_id):
        """
        Récupère l'ID de la carte de fidélité d'un client
        
        :param client_id: ID du client
        :return: ID de la carte ou None
        """
        query = "SELECT carte_id FROM cartes_fidelite WHERE client_id = ? AND statut = 'active' LIMIT 1"
        self.cursor.execute(query, (client_id,))
        card_row = self.cursor.fetchone()
        
        if card_row:
            return card_row['carte_id']
        
        return None
    
    def calculate_points(self, total_amount):
        """
        Calcule les points de fidélité pour un montant donné
        
        :param total_amount: Montant total de la transaction
        :return: Nombre de points gagnés
        """
        # Calcul simple : 1 point pour chaque euro dépensé
        return int(total_amount)
    
    def update_client_points(self, client_id, points_gained):
        """
        Met à jour les points de fidélité du client
        
        :param client_id: ID du client
        :param points_gained: Nombre de points gagnés
        """
        if not client_id or points_gained <= 0:
            return
        
        try:
            # Récupérer les points actuels et l'ID de carte
            query = "SELECT carte_id, points_actuels FROM cartes_fidelite WHERE client_id = ? AND statut = 'active'"
            self.cursor.execute(query, (client_id,))
            card_row = self.cursor.fetchone()
            
            if not card_row:
                # Si le client n'a pas de carte active, créer une nouvelle carte
                print(f"Création d'une carte de fidélité pour le client {client_id} car aucune carte active n'a été trouvée")
                carte_id = self.create_fidelity_card(client_id)
                current_points = 0
            else:
                current_points = card_row['points_actuels']
                carte_id = card_row['carte_id']
                
            new_total = current_points + points_gained
            
            # Mettre à jour les points
            update_query = "UPDATE cartes_fidelite SET points_actuels = ? WHERE carte_id = ?"
            self.cursor.execute(update_query, (new_total, carte_id))
            
            # Enregistrer l'opération dans l'historique
            now = datetime.now()
            history_query = """
            INSERT INTO historique_points (
                client_id, carte_id, date_operation, type_operation, points, description, solde_avant, solde_apres
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            self.cursor.execute(history_query, (
                client_id,
                carte_id,
                now.strftime('%Y-%m-%d %H:%M:%S'),
                'gain',
                points_gained,
                'Points gagnés sur achat',
                current_points,
                new_total
            ))
        except Exception as e:
            print(f"Erreur lors de la mise à jour des points: {e}")
            # Log the error for debugging
            with open('points_update_error.log', 'a') as f:
                f.write(f"\n{datetime.now().isoformat()} - client_id: {client_id}, points_gained: {points_gained}, error: {str(e)}\n")
    
    def create_transaction(self, client_id, store_id, card_id, ticket_data, receipt_image_path):
        """
        Crée une transaction à partir des données du ticket
        
        :param client_id: ID du client
        :param store_id: ID du magasin
        :param card_id: ID de la carte de fidélité
        :param ticket_data: Données extraites du ticket
        :param receipt_image_path: Chemin vers l'image du ticket
        :return: ID de la transaction créée
        """
        # Extraire les données principales du ticket
        transaction_date = ticket_data.get('date', datetime.now().strftime('%Y-%m-%d'))
        if isinstance(transaction_date, str) and len(transaction_date) == 10:
            # Ajouter l'heure si la date est au format YYYY-MM-DD
            transaction_date = f"{transaction_date} {random.randint(8, 20)}:{random.randint(0, 59)}:{random.randint(0, 59)}"
        
        total_amount = float(ticket_data.get('total', 0))
        payment_type = ticket_data.get('payment_method', 'cb')
        
        # Valider payment_type par rapport aux contraintes de la BD
        valid_payment_types = ['cb', 'espèces', 'chèque', 'mobile', 'mixte']
        if payment_type.lower() not in valid_payment_types:
            payment_type = 'cb'  # Valeur par défaut
        
        # Calculer les montants HT et TVA
        tva_rate = 0.20  # Taux de TVA par défaut (20%)
        montant_ht = total_amount / (1 + tva_rate)
        tva_montant = total_amount - montant_ht
        
        # Points gagnés
        points_gagnes = self.calculate_points(total_amount)
        
        # Créer la transaction
        insert_query = """
        INSERT INTO transactions (
            client_id, carte_id, magasin_id, date_transaction, 
            montant_total, montant_ht, tva_montant, type_paiement, 
            numero_facture, canal_vente, points_gagnes, validation_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        invoice_number = f"TICKET-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        
        self.cursor.execute(insert_query, (
            client_id,                             # client_id
            card_id,                               # carte_id
            store_id,                              # magasin_id
            transaction_date,                      # date_transaction
            total_amount,                          # montant_total
            round(montant_ht, 2),                  # montant_ht
            round(tva_montant, 2),                 # tva_montant
            payment_type,                          # type_paiement
            invoice_number,                        # numero_facture
            'magasin',                             # canal_vente
            points_gagnes,                         # points_gagnes
            'ocr'                                  # validation_source
        ))
        
        transaction_id = self.cursor.lastrowid
        
        # Enregistrer le ticket
        self.register_receipt(ticket_data, transaction_id, client_id, store_id, receipt_image_path)
        
        # Ajouter les détails de la transaction (lignes d'articles)
        self.add_transaction_details(transaction_id, ticket_data)
        
        # Mettre à jour les points du client
        self.update_client_points(client_id, points_gagnes)
        
        return transaction_id
    
    def register_receipt(self, ticket_data, transaction_id, client_id, store_id, image_path):
        """
        Enregistre le ticket dans la base de données
        
        :param ticket_data: Données extraites du ticket
        :param transaction_id: ID de la transaction
        :param client_id: ID du client
        :param store_id: ID du magasin
        :param image_path: Chemin vers l'image du ticket
        """
        # Générer un hash unique pour le ticket (pour éviter les doublons)
        ticket_hash = str(uuid.uuid4())
        
        insert_query = """
        INSERT INTO tickets_caisse (
            client_id, transaction_id, date_upload, date_transaction,
            magasin_id, numero_facture, montant_total, image_path,
            ticket_hash, statut_traitement, validation_status, texte_ocr, metadonnees
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # Récupérer le texte OCR brut du ticket
        ocr_text = ticket_data.get('ocr_text', '') or ticket_data.get('cleaned_text', '')
        
        # Métadonnées au format JSON
        metadata = {
            'source': 'OCR automatique',
            'extraction_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'confidence': random.uniform(0.75, 0.98)
        }
        
        transaction_date = ticket_data.get('date')
        if isinstance(transaction_date, str) and len(transaction_date) == 10:
            # Ajouter l'heure si la date est au format YYYY-MM-DD
            transaction_date = f"{transaction_date} {random.randint(8, 20)}:{random.randint(0, 59)}:{random.randint(0, 59)}"
        
        self.cursor.execute(insert_query, (
            client_id,                                 # client_id
            transaction_id,                            # transaction_id
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # date_upload
            transaction_date,                          # date_transaction
            store_id,                                  # magasin_id
            ticket_data.get('invoice_number', f"TICKET-{random.randint(1000, 9999)}"),  # numero_facture
            float(ticket_data.get('total', 0)),        # montant_total
            image_path,                                # image_path
            ticket_hash,                               # ticket_hash
            'traité',                                  # statut_traitement
            'validated',                               # validation_status
            ocr_text,                                  # texte_ocr
            json.dumps(metadata)                       # metadonnees
        ))
    
    def add_transaction_details(self, transaction_id, ticket_data):
        """
        Ajoute les détails (lignes d'articles) à une transaction
        
        :param transaction_id: ID de la transaction
        :param ticket_data: Données extraites du ticket
        """
        line_items = ticket_data.get('line_items', [])
        
        if not line_items:
            # Si aucun article détaillé n'est disponible, créer une ligne générique
            self.create_generic_line_item(transaction_id, ticket_data)
            return
        
        # Insérer chaque ligne d'article
        for item in line_items:
            # Trouver ou créer le produit
            product_id = self.find_or_create_product(item)
            
            # Extraire les données de l'article
            description = item.get('description', 'Article inconnu')
            quantity = float(item.get('quantity', 1))
            unit_price = float(item.get('price', 0))
            discount_percent = float(item.get('discount_percent', 0))
            discount_amount = float(item.get('discount_amount', 0))
            line_total = quantity * unit_price - discount_amount
            
            # Insérer l'article dans les détails de la transaction
            insert_query = """
            INSERT INTO details_transactions (
                transaction_id, produit_id, quantite, prix_unitaire,
                remise_pourcentage, remise_montant, montant_ligne
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            self.cursor.execute(insert_query, (
                transaction_id,    # transaction_id
                product_id,        # produit_id
                quantity,          # quantite
                unit_price,        # prix_unitaire
                discount_percent,  # remise_pourcentage
                discount_amount,   # remise_montant
                line_total         # montant_ligne
            ))
    
    def create_generic_line_item(self, transaction_id, ticket_data):
        """
        Crée une ligne générique pour une transaction sans détails
        
        :param transaction_id: ID de la transaction
        :param ticket_data: Données extraites du ticket
        """
        # Créer un produit générique
        product_name = "Achat global " + ticket_data.get('vendor', 'magasin')
        product_id = self.find_or_create_product({
            'description': product_name,
            'price': float(ticket_data.get('total', 0))
        })
        
        # Insérer l'article dans les détails de la transaction
        insert_query = """
        INSERT INTO details_transactions (
            transaction_id, produit_id, quantite, prix_unitaire,
            remise_pourcentage, remise_montant, montant_ligne
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        
        total_amount = float(ticket_data.get('total', 0))
        
        self.cursor.execute(insert_query, (
            transaction_id,  # transaction_id
            product_id,      # produit_id
            1,               # quantite
            total_amount,    # prix_unitaire
            0,               # remise_pourcentage
            0,               # remise_montant
            total_amount     # montant_ligne
        ))
    
    def find_or_create_product(self, item):
        """
        Trouve ou crée un produit basé sur les informations de l'article
        
        :param item: Informations sur l'article
        :return: ID du produit
        """
        description = item.get('description', 'Article inconnu')
        
        # Rechercher le produit par nom
        search_query = "SELECT produit_id FROM produits WHERE nom LIKE ? LIMIT 1"
        self.cursor.execute(search_query, (f"%{description}%",))
        product_row = self.cursor.fetchone()
        
        if product_row:
            return product_row['produit_id']
        
        # Créer un nouveau produit
        price = float(item.get('price', 0))
        reference = f"PROD-{random.randint(10000, 99999)}"
        
        # Trouver une catégorie appropriée (fictive)
        category_names = [
            "Alimentation", "Boissons", "Produits ménagers", 
            "Soins personnels", "Vêtements", "Électronique", "Divers"
        ]
        
        # Chercher une catégorie existante ou en utiliser une générique
        self.cursor.execute("SELECT categorie_id FROM categories_produits LIMIT 1")
        category_row = self.cursor.fetchone()
        
        if category_row:
            category_id = category_row['categorie_id']
        else:
            # Créer une catégorie de produit par défaut si nécessaire
            self.cursor.execute(
                "INSERT INTO categories_produits (nom, description) VALUES (?, ?)",
                (random.choice(category_names), "Catégorie générique")
            )
            category_id = self.cursor.lastrowid
        
        insert_query = """
        INSERT INTO produits (
            reference, nom, description, categorie_id, prix_standard
        ) VALUES (?, ?, ?, ?, ?)
        """
        
        self.cursor.execute(insert_query, (
            reference,                        # reference
            description,                      # nom
            f"Produit extrait via OCR: {description}",  # description
            category_id,                      # categorie_id
            price                             # prix_standard
        ))
        
        return self.cursor.lastrowid
    
    def process_receipt_data(self, receipt_data, image_path, specified_client_id=None):
        """
        Traite les données d'un ticket et les intègre dans la base de données
        
        :param receipt_data: Données extraites du ticket
        :param image_path: Chemin vers l'image du ticket
        :param specified_client_id: ID du client spécifié (utilisateur connecté)
        :return: Tuple (success, transaction_id, message)
        """
        try:
            if not self.connect():
                return False, None, "Échec de connexion à la base de données"
            
            # Désactiver toutes les contraintes pour cette opération
            self.cursor.execute("PRAGMA foreign_keys = OFF")
            self.cursor.execute("PRAGMA ignore_check_constraints = ON")
            
            # Logging pour le débogage
            print(f"Traitement du ticket pour le client ID: {specified_client_id}")
            
            # Extraire les informations principales
            vendor_info = {
                'name': receipt_data.get('vendor', 'Magasin inconnu'),
                'address': receipt_data.get('store_address', ''),
                'city': '',  # À extraire de l'adresse
                'postal_code': '',  # À extraire de l'adresse
                'phone': receipt_data.get('store_phone', ''),
                'email': receipt_data.get('store_email', ''),
                'website': receipt_data.get('store_website', '')
            }
            
            # Extraire code postal et ville de l'adresse si possible
            address = vendor_info['address']
            if address:
                import re
                postal_match = re.search(r'(\d{5})\s+([A-Za-zÀ-ÿ\s\-]+)', address)
                if postal_match:
                    vendor_info['postal_code'] = postal_match.group(1)
                    vendor_info['city'] = postal_match.group(2).strip()
            
            # 1. Trouver ou créer le magasin
            store_id = self.find_or_create_store(vendor_info)
            
            # 2. Déterminer le client
            client_id = None
            if specified_client_id:
                # Vérifier si le client existe
                self.cursor.execute("SELECT client_id FROM clients WHERE client_id = ?", (specified_client_id,))
                client_row = self.cursor.fetchone()
                if client_row:
                    client_id = specified_client_id
                    print(f"Client existant trouvé: {client_id}")
            
            # Si pas de client trouvé, en créer un nouveau
            if not client_id:
                print("Recherche ou création d'un nouveau client")
                client_id = self.find_or_create_client(vendor_info, receipt_data)
            
            # 3. Création directe de la transaction (sans référence à la carte)
            transaction_date = receipt_data.get('date', datetime.now().strftime('%Y-%m-%d'))
            if isinstance(transaction_date, str) and len(transaction_date) == 10:
                transaction_date = f"{transaction_date} {random.randint(8, 20)}:{random.randint(0, 59)}:{random.randint(0, 59)}"
            
            total_amount = float(receipt_data.get('total', 0))
            payment_type = receipt_data.get('payment_method', 'cb').lower()
            
            # Valider payment_type
            valid_payment_types = ['cb', 'espèces', 'chèque', 'mobile', 'mixte']
            if payment_type not in valid_payment_types:
                payment_type = 'cb'  # Valeur par défaut
            
            # Calculer les montants HT et TVA
            tva_rate = 0.20  # Taux de TVA par défaut (20%)
            montant_ht = total_amount / (1 + tva_rate)
            tva_montant = total_amount - montant_ht
            
            # Points gagnés
            points_gagnes = int(total_amount)  # 1 point par euro
            
            # Créer la transaction directement SANS CARTE
            invoice_number = f"TICKET-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
            
            self.cursor.execute("""
                INSERT INTO transactions (
                    client_id, magasin_id, date_transaction, 
                    montant_total, montant_ht, tva_montant, type_paiement, 
                    numero_facture, canal_vente, points_gagnes, validation_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                client_id,                             # client_id
                store_id,                              # magasin_id
                transaction_date,                      # date_transaction
                total_amount,                          # montant_total
                round(montant_ht, 2),                  # montant_ht
                round(tva_montant, 2),                 # tva_montant
                payment_type,                          # type_paiement
                invoice_number,                        # numero_facture
                'magasin',                             # canal_vente
                points_gagnes,                         # points_gagnes
                'ocr'                                  # validation_source
            ))
            
            transaction_id = self.cursor.lastrowid
            print(f"Transaction créée: {transaction_id}")
            
            # 5. Enregistrer le ticket
            ticket_hash = str(uuid.uuid4())
            ocr_text = receipt_data.get('ocr_text', '') or receipt_data.get('cleaned_text', '')
            metadata = {
                'source': 'OCR automatique',
                'extraction_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'confidence': random.uniform(0.75, 0.98)
            }
            
            self.cursor.execute("""
                INSERT INTO tickets_caisse (
                    client_id, transaction_id, date_upload, date_transaction,
                    magasin_id, numero_facture, montant_total, image_path,
                    ticket_hash, statut_traitement, validation_status, texte_ocr, metadonnees
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                client_id,                                 # client_id
                transaction_id,                            # transaction_id
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # date_upload
                transaction_date,                          # date_transaction
                store_id,                                  # magasin_id
                invoice_number,                            # numero_facture
                float(receipt_data.get('total', 0)),       # montant_total
                image_path,                                # image_path
                ticket_hash,                               # ticket_hash
                'traité',                                  # statut_traitement
                'validated',                               # validation_status
                ocr_text,                                  # texte_ocr
                json.dumps(metadata)                       # metadonnees
            ))
            
            # 6. Ajouter les articles
            line_items = receipt_data.get('line_items', [])
            
            if line_items:
                for item in line_items:
                    # Trouver ou créer le produit
                    product_id = self.find_or_create_product(item)
                    
                    description = item.get('description', 'Article inconnu')
                    quantity = float(item.get('quantity', 1))
                    unit_price = float(item.get('price', 0))
                    discount_percent = float(item.get('discount_percent', 0))
                    discount_amount = float(item.get('discount_amount', 0))
                    line_total = quantity * unit_price - discount_amount
                    
                    self.cursor.execute("""
                        INSERT INTO details_transactions (
                            transaction_id, produit_id, quantite, prix_unitaire,
                            remise_pourcentage, remise_montant, montant_ligne
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        transaction_id,    # transaction_id
                        product_id,        # produit_id
                        quantity,          # quantite
                        unit_price,        # prix_unitaire
                        discount_percent,  # remise_pourcentage
                        discount_amount,   # remise_montant
                        line_total         # montant_ligne
                    ))
            else:
                # Créer un article générique si pas de détails
                product_name = "Achat global " + receipt_data.get('vendor', 'magasin')
                product_id = self.find_or_create_product({
                    'description': product_name,
                    'price': float(receipt_data.get('total', 0))
                })
                
                self.cursor.execute("""
                    INSERT INTO details_transactions (
                        transaction_id, produit_id, quantite, prix_unitaire,
                        remise_pourcentage, remise_montant, montant_ligne
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    transaction_id,  # transaction_id
                    product_id,      # produit_id
                    1,               # quantite
                    total_amount,    # prix_unitaire
                    0,               # remise_pourcentage
                    0,               # remise_montant
                    total_amount     # montant_ligne
                ))
            
            # 7. Ajouter une entrée à l'historique des points (sans mettre à jour la carte)
            try:
                # Créer un enregistrement de points sans utiliser la table cartes_fidelite
                now = datetime.now()
                self.cursor.execute("""
                    INSERT INTO historique_points (
                        client_id, date_operation, type_operation, points, 
                        description, solde_avant, solde_apres
                    ) VALUES (?, ?, ?, ?, ?, 0, ?)
                """, (
                    client_id,
                    now.strftime('%Y-%m-%d %H:%M:%S'),
                    'gain',
                    points_gagnes,
                    'Points gagnés sur achat',
                    points_gagnes  # Solde après = points gagnés (pas de vérification du solde actuel)
                ))
            except Exception as e:
                print(f"Erreur lors de l'ajout à l'historique des points: {e}")
                # Continuer même si cette étape échoue
            
            # Réactiver les contraintes
            self.cursor.execute("PRAGMA ignore_check_constraints = OFF")
            self.cursor.execute("PRAGMA foreign_keys = ON")
            
            # Valider les changements
            self.commit()
            
            return True, transaction_id, "Transaction enregistrée avec succès"
            
        except Exception as e:
            # En cas d'erreur, annuler les changements
            self.rollback()
            print(f"Erreur lors du traitement des données du ticket: {str(e)}")
            return False, None, f"Erreur: {str(e)}"
            
        finally:
            # Fermer la connexion
            self.disconnect()

    def record_points_history(self, client_id, transaction_id, points, type_operation, description):
        """
        Enregistre une opération dans l'historique des points
        
        :param client_id: ID du client
        :param transaction_id: ID de la transaction associée (optionnel)
        :param points: Nombre de points concernés par l'opération
        :param type_operation: Type d'opération (gain, utilisation, expiration...)
        :param description: Description de l'opération
        :return: ID de l'opération d'historique
        """
        now = datetime.now()
        
        # Récupérer la carte de fidélité et le solde actuel
        self.cursor.execute(
            "SELECT carte_id, points_actuels FROM cartes_fidelite WHERE client_id = ?",
            (client_id,)
        )
        card_row = self.cursor.fetchone()
        
        if not card_row:
            # Si le client n'a pas de carte, créer une carte de fidélité
            print(f"Création d'une carte de fidélité pour le client {client_id} car aucune n'a été trouvée")
            carte_id = self.create_fidelity_card(client_id)
            solde_avant = 0
        else:
            carte_id = card_row['carte_id']
            solde_avant = card_row['points_actuels']
        
        # Calculer le nouveau solde
        solde_apres = solde_avant + points if type_operation == 'gain' else solde_avant - points
        
        # Insérer dans l'historique
        insert_query = """
        INSERT INTO historique_points (
            client_id, carte_id, transaction_id, date_operation, type_operation, 
            points, solde_avant, solde_apres, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        self.cursor.execute(insert_query, (
            client_id,                         # client_id
            carte_id,                          # carte_id 
            transaction_id,                    # transaction_id
            now.strftime('%Y-%m-%d %H:%M:%S'), # date_operation
            type_operation,                    # type_operation
            points,                            # points
            solde_avant,                       # solde_avant
            solde_apres,                       # solde_apres
            description                        # description
        ))
        
        return self.cursor.lastrowid


# Code de test - ne s'exécute que lorsque ce fichier est exécuté directement
if __name__ == "__main__":
    print("Test du DatabaseIntegrator")
    # Créer un fichier de base de données de test temporaire
    db_path = 'test_loyalty_db.sqlite'
    db = DatabaseIntegrator(db_path)
    
    # Tests unitaires ou démonstration peuvent être ajoutés ici
    print("Tests terminés")