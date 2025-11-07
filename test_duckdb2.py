import duckdb
import pandas as pd

conn = duckdb.connect(':memory:')
conn.execute('CREATE TABLE test (id INT, name VARCHAR)')
conn.execute('INSERT INTO test VALUES (1, "Alice"), (2, "Bob")')

rel = conn.execute('SELECT * FROM test')
print("Relation type:", type(rel))
print("Relation methods:", [x for x in dir(rel) if not x.startswith('_')])

# Try to get data
rows = rel.fetchall() if hasattr(rel, 'fetchall') else None
print("Rows:", rows)

# Try fetching all and converting to pandas
all_data = rel.fetchall() if hasattr(rel, 'fetchall') else []
print("All data:", all_data)

# Try using arrow
arrow_available = hasattr(rel, 'arrow')
print("Arrow available:", arrow_available)

# Get description
desc = rel.description if hasattr(rel, 'description') else None
print("Description:", desc)

# Convert manually
if all_data and desc:
    df = pd.DataFrame(all_data, columns=[d[0] for d in desc])
    print("DataFrame:", df)
