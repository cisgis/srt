import sqlite3
conn = sqlite3.connect('data/srt.db')
c = conn.cursor()

c.execute('PRAGMA foreign_keys=OFF')

c.execute('CREATE TABLE IF NOT EXISTS Clients_old AS SELECT * FROM Clients WHERE 1=0')

c.execute('PRAGMA foreign_keys=ON')
conn.commit()
print('Created Clients_old table')
conn.close()