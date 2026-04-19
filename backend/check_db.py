import sqlite3
import os

db_path = 'finrag.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    count = 0
    for table in tables:
        table_name = table[0]
        try:
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [col[1] for col in cursor.fetchall()]
            
            for row in rows:
                for idx, col in enumerate(row):
                    if isinstance(col, str) and "Voyage" in col:
                        print(f"FOUND IN TABLE: {table_name}, COLUMN: {columns[idx]}")
                        print(f"Content length: {len(col)}, ID: {row[0]}")
                        
                        if 'analysis' == columns[idx]:
                            # Just remove all voyage text dynamically for safety
                            import re
                            # Remove the disclaimer paragraph
                            new_text = re.sub(r'\*This analysis was generated using AI-powered document extraction with \*\*Voyage AI.*?\*', '', col, flags=re.DOTALL | re.IGNORECASE)
                            cursor.execute(f"UPDATE {table_name} SET analysis = ? WHERE id = ?", (new_text, row[0]))
                            count += 1
        except Exception as e:
            pass
            
    if count > 0:
        conn.commit()
    print(f'Updated {count} records.')
else:
    print('Not found')
