import requests
import sqlite3

c = sqlite3.connect('inner_echoes.db')
c.execute("DELETE FROM users WHERE username='mrtest'")
c.commit()

s = requests.Session()
s.post('http://127.0.0.1:5000/signup', data={'username': 'mrtest', 'password': '123', 'full_name': 'Test', 'email': 'test@test.com'})
r = s.post('http://127.0.0.1:5000/login', data={'username': 'mrtest', 'password': '123'})

files = {'profile_pic': ('mypic.jpg', b'000', 'image/jpeg')}
data = {'full_name': 'Test Edit'}
s.post('http://127.0.0.1:5000/edit_profile', files=files, data=data)

c = sqlite3.connect('inner_echoes.db').cursor()
c.execute("SELECT profile_pic FROM users WHERE username='mrtest'")
print('Final DB Pic:', c.fetchone())
