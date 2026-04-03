import requests
import sqlite3

session = requests.Session()
r = session.post('http://127.0.0.1:5000/login', data={'username': 'pranaya', 'password': '123'})
print('Login Status:', r.status_code)

files = {'profile_pic': ('test_pic.jpg', b'dummy content', 'image/jpeg')}
data = {'full_name': 'Pranaya Varshini', 'bio': 'New bio test'}

print('Posting edit_profile...')
r = session.post('http://127.0.0.1:5000/edit_profile', files=files, data=data)
print('Edit Profile Status:', r.status_code)

conn = sqlite3.connect('inner_echoes.db')
c = conn.cursor()
c.execute("SELECT profile_pic FROM users WHERE username='pranaya'")
row = c.fetchone()
print('DB Pic:', row)

import os
if row and row[0]:
    print('File exists on disk?', os.path.exists(os.path.join('static', 'uploads', row[0])))
