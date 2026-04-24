import sqlite3
conn = sqlite3.connect('data/srt.db')
c = conn.cursor()

c.execute('PRAGMA foreign_keys=OFF')
c.execute('DROP TABLE IF EXISTS Clients_old')
c.execute('PRAGMA foreign_keys=ON')
conn.commit()
print('Removed Clients_old table')
conn.close()