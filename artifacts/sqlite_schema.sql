CREATE TABLE enzymes (
            ec_number TEXT PRIMARY KEY,
            enzyme_id TEXT,
            recommended_name TEXT,
            systematic_name TEXT,
            reaction_summary TEXT,
            protein_count INTEGER,
            synonym_count INTEGER,
            reaction_count INTEGER,
            km_count INTEGER,
            turnover_count INTEGER,
            inhibitor_count INTEGER
        );
CREATE TABLE proteins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ec_number TEXT NOT NULL,
            protein_id TEXT,
            organism TEXT,
            comment TEXT,
            reference_ids TEXT,
            raw_json TEXT,
            FOREIGN KEY (ec_number) REFERENCES enzymes(ec_number)
        );
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE enzyme_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ec_number TEXT NOT NULL,
            category TEXT NOT NULL,
            value TEXT,
            value_numeric_low REAL,
            value_numeric_high REAL,
            unit TEXT,
            context TEXT,
            comment TEXT,
            proteins TEXT,
            reference_ids TEXT,
            raw_json TEXT,
            FOREIGN KEY (ec_number) REFERENCES enzymes(ec_number)
        );
CREATE TABLE text_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ec_number TEXT NOT NULL,
            field_code TEXT NOT NULL,
            field_name TEXT,
            value_raw TEXT,
            value_text TEXT,
            protein_tokens TEXT,
            reference_tokens TEXT,
            qualifiers TEXT,
            FOREIGN KEY (ec_number) REFERENCES enzymes(ec_number)
        );
CREATE INDEX idx_proteins_ec ON proteins (ec_number);
CREATE INDEX idx_facts_ec ON enzyme_facts (ec_number);
CREATE INDEX idx_facts_category ON enzyme_facts (category);
CREATE INDEX idx_facts_value ON enzyme_facts (value);
CREATE INDEX idx_text_ec ON text_facts (ec_number);
CREATE INDEX idx_text_code ON text_facts (field_code);
