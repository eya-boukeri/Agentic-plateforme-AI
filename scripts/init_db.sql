-- scripts/init_db.sql
-- Ce script est exécuté automatiquement au premier démarrage de PostgreSQL

-- ============================================================
-- 1. TABLE : hauteurs_brutes (capteur I1 - instantané)
-- ============================================================
CREATE TABLE IF NOT EXISTS hauteurs_brutes (
    id SERIAL PRIMARY KEY,
    code_station VARCHAR(20),
    date_heure TIMESTAMP,
    hauteur_cm DECIMAL(10,3),
    capteur VARCHAR(10),
    origine VARCHAR(10),
    qualite VARCHAR(20),
    date_import TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 2. TABLE : debits_journaliers_bruts (capteur J1 - journalier)
-- ============================================================
CREATE TABLE IF NOT EXISTS debits_journaliers_bruts (
    id SERIAL PRIMARY KEY,
    code_station VARCHAR(20),
    jour DATE,
    debit_m3s DECIMAL(10,3),
    capteur VARCHAR(10),
    origine VARCHAR(10),
    qualite VARCHAR(20),
    date_import TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 3. TABLE : courbes_tarage (pour convertir hauteur → débit)
-- ============================================================
CREATE TABLE IF NOT EXISTS courbes_tarage (
    id SERIAL PRIMARY KEY,
    code_station VARCHAR(20),
    hauteur_cm DECIMAL(10,3),
    debit_m3s DECIMAL(10,3),
    date_validite DATE,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 4. TABLE : debits_instantanés (calculés à partir des hauteurs)
-- ============================================================
CREATE TABLE IF NOT EXISTS debits_instantanés (
    id SERIAL PRIMARY KEY,
    code_station VARCHAR(20),
    date_heure TIMESTAMP,
    hauteur_cm DECIMAL(10,3),
    debit_m3s DECIMAL(10,3),
    date_calcul TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 5. TABLE : debits_journaliers (agrégation journalière)
-- ============================================================
CREATE TABLE IF NOT EXISTS debits_journaliers (
    id SERIAL PRIMARY KEY,
    code_station VARCHAR(20),
    jour DATE,
    hauteur_moyenne DECIMAL(10,3),
    hauteur_max DECIMAL(10,3),
    hauteur_min DECIMAL(10,3),
    debit_moyen DECIMAL(10,3),
    debit_max DECIMAL(10,3),
    debit_min DECIMAL(10,3),
    debit_instantane_max DECIMAL(10,3),
    date_heure_max TIMESTAMP,
    debit_instantane_min DECIMAL(10,3),
    date_heure_min TIMESTAMP,
    nb_mesures INTEGER,
    source VARCHAR(10) DEFAULT 'I1',
    annee INTEGER,
    date_calcul TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 6. TABLE : statistiques_annuelles (résultats finaux)
-- ============================================================
CREATE TABLE IF NOT EXISTS statistiques_annuelles (
    id SERIAL PRIMARY KEY,
    code_station VARCHAR(20),
    annee INTEGER,
    debit_moyen DECIMAL(10,3),
    debit_max_jour DECIMAL(10,3),
    date_max_jour DATE,
    debit_min_jour DECIMAL(10,3),
    date_min_jour DATE,
    debit_max_inst DECIMAL(10,3),
    date_max_inst TIMESTAMP,
    debit_min_inst DECIMAL(10,3),
    date_min_inst TIMESTAMP,
    volume_total_hm3 DECIMAL(10,2),
    lame_ecoulee_mm DECIMAL(8,2),
    dc1 DECIMAL(10,3),
    dc3 DECIMAL(10,3),
    dc6 DECIMAL(10,3),
    dc9 DECIMAL(10,3),
    dc11 DECIMAL(10,3),
    dce DECIMAL(10,3),
    dcc DECIMAL(10,3),
    q10 DECIMAL(10,3),
    q50 DECIMAL(10,3),
    q90 DECIMAL(10,3),
    q95 DECIMAL(10,3),
    nb_jours_presents INTEGER,
    taux_remplissage DECIMAL(5,2),
    qualite_station VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 7. TABLE : crues (caractéristiques des crues)
-- ============================================================
CREATE TABLE IF NOT EXISTS crues (
    id SERIAL PRIMARY KEY,
    code_station VARCHAR(20),
    annee INTEGER,
    date_debut TIMESTAMP,
    date_fin TIMESTAMP,
    temps_base_min INTEGER,
    temps_montee_min INTEGER,
    debit_debut DECIMAL(10,3),
    debit_fin DECIMAL(10,3),
    debit_max_m3s DECIMAL(10,3),
    volume_ecoule_hm3 DECIMAL(10,4),
    volume_ruiss_hm3 DECIMAL(10,4),
    lame_ecoulee_mm DECIMAL(8,3),
    lame_ruiss_mm DECIMAL(8,3),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 8. TABLE : anomalies (pour le rapport de validation)
-- ============================================================
CREATE TABLE IF NOT EXISTS anomalies (
    id SERIAL PRIMARY KEY,
    code_station VARCHAR(20),
    date DATE,
    debit_brut DECIMAL(10,3),
    type_anomalie VARCHAR(50),
    gravite VARCHAR(20),
    description TEXT,
    action_prise VARCHAR(50),
    date_detection TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_hauteurs_station_date ON hauteurs_brutes(code_station, date_heure);
CREATE INDEX idx_debits_journaliers_station ON debits_journaliers(code_station, jour);
CREATE INDEX idx_stats_station_annee ON statistiques_annuelles(code_station, annee);
CREATE INDEX idx_crues_station_annee ON crues(code_station, annee);

-- ============================================================
-- MESSAGE
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE '✅ Tables créées avec succès !';
END $$;