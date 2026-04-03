from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import os
import calendar
from datetime import datetime
from collections import Counter
from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

try:
    from markdown import markdown
except ImportError:
    markdown = None


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'inner_echoes_secret_key_2024')

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DB_FILE = 'inner_echoes.db'
enc_key_str = os.environ.get('ENCRYPTION_KEY', 'cw_0x689RpI-jtRR7oE8h_eQsKImvJapLeSbXpwF4e4=')
cipher = Fernet(enc_key_str.encode() if isinstance(enc_key_str, str) else enc_key_str)


def encrypt_text(text):
    return cipher.encrypt(text.encode()).decode()


def decrypt_text(encrypted_text):
    return cipher.decrypt(encrypted_text.encode()).decode()


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        full_name TEXT,
        email TEXT,
        bio TEXT,
        profile_pic TEXT,
        joined_date TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        title TEXT,
        content TEXT,
        mood TEXT,
        date TEXT,
        file TEXT,
        tags TEXT,
        FOREIGN KEY (username) REFERENCES users (username)
    )''')
    # Add tags column if not exists
    try:
        c.execute('ALTER TABLE entries ADD COLUMN tags TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Add bio and profile_pic columns if not exists
    try:
        c.execute('ALTER TABLE users ADD COLUMN bio TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        c.execute('ALTER TABLE users ADD COLUMN profile_pic TEXT')
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()


def load_users():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, password, full_name, email, joined_date FROM users')
    rows = c.fetchall()
    conn.close()
    users = {}
    for row in rows:
        users[row[0]] = {
            'password': row[1],
            'full_name': row[2],
            'email': row[3],
            'joined_date': row[4]
        }
    return users



def get_user_entries(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, title, content, mood, date, file, tags FROM entries WHERE username = ? ORDER BY date DESC', (username,))
    rows = c.fetchall()
    conn.close()
    entries = []
    for row in rows:
        try:
            decrypted_content = decrypt_text(row[2])
        except Exception as e:
            print(f"Decryption failed for entry {row[0]}: {e}")
            decrypted_content = "[Content could not be decrypted - this entry may be corrupted]"
        entries.append({
            'id': row[0],
            'title': row[1],
            'content': decrypted_content,
            'mood': row[3],
            'date': row[4],
            'file': row[5],
            'tags': row[6] or ''
        })
    return entries


def save_entry(entry):
    encrypted_content = encrypt_text(entry['content'])
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO entries (username, title, content, mood, date, file, tags) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (entry['username'], entry['title'], encrypted_content, entry['mood'], entry['date'], entry['file'], entry.get('tags', '')))
    conn.commit()
    conn.close()


def delete_entry_db(username, entry_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM entries WHERE username = ? AND id = ?', (username, entry_id))
    conn.commit()
    conn.close()


# 🏠 Home page - Redirect to login if not authenticated
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect('/login')
    
    username = session.get('username')
    entries = get_user_entries(username)
    
    # Get year and month from request or use current
    year = request.args.get('year', default=datetime.now().year, type=int)
    month = request.args.get('month', default=datetime.now().month, type=int)
    
    # Validate month/year
    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1
    
    # Create calendar
    cal = calendar.monthcalendar(year, month)
    
    # Create a dict of date -> list of moods for entries in this month
    entry_moods = {}
    for entry in entries:
        entry_date = datetime.strptime(entry['date'], '%Y-%m-%d')
        if entry_date.year == year and entry_date.month == month:
            mood_value = entry.get('mood', 'happy')
            if mood_value == 'sappy':
                mood_value = 'deep'
            if entry['date'] not in entry_moods:
                entry_moods[entry['date']] = []
            entry_moods[entry['date']].append(mood_value)

    recent_entries = sorted(entries, key=lambda e: e['date'], reverse=True)[:5]
    flash_msg = session.pop('flash', None)
    return render_template('index.html', entries=entries, cal=cal, year=year, month=month,
                           entry_moods=entry_moods, datetime=datetime,
                           recent_entries=recent_entries, current_mood=session.get('mood', 'happy'),
                           flash_msg=flash_msg)


@app.route('/search', methods=['GET', 'POST'])
def search():
    if not session.get('logged_in'):
        return redirect('/login')
    username = session.get('username')
    query = request.args.get('q', '')
    mood_filter = request.args.get('mood', 'all')
    tag_filter = request.args.get('tag', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    entries = get_user_entries(username)
    
    # Apply filters
    if query:
        entries = [e for e in entries if query.lower() in e['title'].lower() or query.lower() in e['content'].lower() or query.lower() in e['tags'].lower()]
    if mood_filter != 'all':
        entries = [e for e in entries if e['mood'] == mood_filter]
    if tag_filter:
        entries = [e for e in entries if tag_filter.lower() in e['tags'].lower()]
    if date_from:
        entries = [e for e in entries if e['date'] >= date_from]
    if date_to:
        entries = [e for e in entries if e['date'] <= date_to]

    return render_template('search.html', entries=entries, query=query, mood_filter=mood_filter, tag_filter=tag_filter, date_from=date_from, date_to=date_to, current_mood=session.get('mood', 'happy'))


@app.route('/analytics')
def analytics():
    if not session.get('logged_in'):
        return redirect('/login')
    username = session.get('username')
    entries = get_user_entries(username)
    
    # Mood trends
    mood_counts = Counter([e['mood'] for e in entries])
    mood_data = [{'mood': k, 'count': v} for k, v in mood_counts.items()]
    
    # Writing streak
    dates = sorted(set([e['date'] for e in entries]))
    streak = 0
    max_streak = 0
    current_streak = 0
    prev_date = None
    for date_str in dates:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        if prev_date and (date - prev_date).days == 1:
            current_streak += 1
        else:
            current_streak = 1
        max_streak = max(max_streak, current_streak)
        prev_date = date
    streak = current_streak if dates and (datetime.now() - datetime.strptime(dates[-1], '%Y-%m-%d')).days <= 1 else 0
    
    # Analytics for Timeline Trend Chart
    timeline_dict = {}
    for e in entries:
        d = e['date']
        if d not in timeline_dict:
            timeline_dict[d] = []
        timeline_dict[d].append(e['mood'])
    
    mood_score_map = {'excited': 3, 'happy': 2, 'calm': 1, 'bored': 0, 'sad': -1, 'anxious': -2, 'angry': -3, 'deep': 0, 'sappy': 0}
    timeline_data = []
    # Provide the last 30 distinct entry dates
    for d in sorted(timeline_dict.keys())[-30:]:
        scores = [mood_score_map.get(m, 0) for m in timeline_dict[d]]
        avg_score = sum(scores) / len(scores)
        timeline_data.append({'date': d, 'score': avg_score})

    return render_template('analytics.html', mood_data=mood_data, streak=streak, max_streak=max_streak, total_entries=len(entries), timeline_data=timeline_data)


@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    print(f"edit_profile called, method: {request.method}, logged_in: {session.get('logged_in')}")
    if not session.get('logged_in'):
        return redirect('/login')
    
    username = session.get('username')
    print(f"Username: {username}")
    if request.method == 'POST':
        full_name = request.form.get('full_name', '')
        email = request.form.get('email', '')
        bio = request.form.get('bio', '')
        print(f"Form data: full_name={full_name}, email={email}, bio={bio}")
        
        # Get current profile_pic
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT profile_pic FROM users WHERE username = ?', (username,))
        current_pic_row = c.fetchone()
        
        if not current_pic_row:
            conn.close()
            session.clear()
            flash('Session expired. Please log in again.', 'warning')
            return redirect('/login')
            
        current_profile_pic = current_pic_row[0]
        conn.close()
        
        # Handle profile picture upload
        profile_pic_filename = current_profile_pic  # Preserve existing by default
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename:
                # Get file extension
                _, ext = os.path.splitext(file.filename)
                if not ext:
                    ext = '.jpg'  # Default to jpg if no extension
                
                # Save the file with original extension
                filename = f"{username}_profile_{int(datetime.now().timestamp())}{ext}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Ensure uploads directory exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                try:
                    file.save(file_path)
                    profile_pic_filename = filename
                except Exception as e:
                    print(f"Error saving profile picture: {e}")
                    profile_pic_filename = current_profile_pic  # Keep existing on error
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Update user info
        try:
            c.execute('UPDATE users SET full_name = ?, email = ?, bio = ?, profile_pic = ? WHERE username = ?',
                      (full_name, email, bio, profile_pic_filename, username))
            conn.commit()
            print("Profile updated successfully")
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            print(f"Database update error: {e}")
            conn.rollback()
            flash('Error updating profile. Please try again.', 'error')
        
        conn.close()
        return redirect('/profile')
    
    # GET
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT full_name, email, bio, profile_pic FROM users WHERE username = ?', (username,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        session.clear()
        flash('Session expired. Please log in again.', 'warning')
        return redirect('/login')
    
    user_data = {
        'full_name': row[0] if row[0] else '',
        'email': row[1] if row[1] else '',
        'bio': row[2] if row[2] else '',
        'profile_pic': row[3] if row[3] else None
    }
    
    conn.close()
    return render_template('edit_profile.html', user_data=user_data)


@app.route('/journal')
def journal():
    if not session.get('logged_in'):
        return redirect('/login')
    username = session.get('username')
    mood_filter = request.args.get('mood', 'all')
    entries = sorted(get_user_entries(username), key=lambda e: e['date'], reverse=True)
    if mood_filter != 'all':
        entries = [e for e in entries if e.get('mood') == mood_filter]
    return render_template('journal.html', entries=entries, current_mood=session.get('mood', 'happy'), mood_filter=mood_filter)


@app.route('/delete/<int:id>')
def delete_entry(id):
    if not session.get('logged_in'):
        return redirect('/login')
    username = session.get('username')
    delete_entry_db(username, id)
    return redirect('/journal')


@app.route('/uploads')
def uploads():
    if not session.get('logged_in'):
        return redirect('/login')
    username = session.get('username')
    entries = get_user_entries(username)
    files = [e['file'] for e in entries if e.get('file')]
    return render_template('uploads.html', files=files, current_mood=session.get('mood', 'happy'))


@app.route('/mood')
def mood():
    if not session.get('logged_in'):
        return redirect('/login')
    entries = get_user_entries(session.get('username'))
    mood_summary = Counter([e['mood'] for e in entries])
    top_mood = mood_summary.most_common(1)[0][0] if mood_summary else 'calm'
    return render_template('mood.html', mood_summary=mood_summary, top_mood=top_mood, current_mood=session.get('mood', 'happy'))


# 📅 View entries for a specific date
@app.route('/entry/<date>')
def view_entry(date):
    if not session.get('logged_in'):
        return redirect('/login')
    
    username = session.get('username')
    entries = get_user_entries(username)
    
    # Filter entries for the date
    day_entries = [e for e in entries if e['date'] == date]

    # Markdown render if available
    for entry in day_entries:
        if markdown:
            entry['content_html'] = markdown(entry.get('content', ''), extensions=['fenced_code', 'nl2br'])
        else:
            entry['content_html'] = entry.get('content', '').replace('\n', '<br>')
    
    return render_template('entry.html', entries=day_entries, date=date)


# ✏️ Edit entry
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_entry(id):
    if not session.get('logged_in'):
        return redirect('/login')

    username = session.get('username')
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        mood = request.form['mood']
        new_date = request.form['date']
        tags = request.form.get('tags', '')

        encrypted_content = encrypt_text(content)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('UPDATE entries SET title = ?, content = ?, mood = ?, date = ?, tags = ? WHERE id = ? AND username = ?',
                  (title, encrypted_content, mood, new_date, tags, id, username))
        conn.commit()
        conn.close()
        return redirect(f'/entry/{new_date}')

    # GET
    entries = get_user_entries(username)
    entry = next((e for e in entries if e['id'] == id), None)
    if not entry:
        return redirect('/')

    return render_template('edit.html', entry=entry)


# ➕ Add entry page
@app.route('/add', methods=['GET', 'POST'])
def add():
    if not session.get('logged_in'):
        return redirect('/login')
    
    if request.method == 'POST':
        username = session.get('username')
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        mood = request.form.get('mood', session.get('mood', 'happy'))
        date = request.form.get('date', '').strip() or datetime.now().strftime('%Y-%m-%d')

        # Evaluate permissions and normalize mood value
        allowed_moods = ['happy', 'sad', 'sappy', 'deep', 'bored', 'anxious', 'angry', 'excited']
        mood = (mood.strip() if isinstance(mood, str) else '').lower() or session.get('mood', 'happy')
        if mood not in allowed_moods:
            mood = session.get('mood', 'happy')
        if mood == 'sappy':
            mood = 'deep'

        if not title:
            title = 'Untitled Reflection'

        if content is None:
            content = ''

        file = request.files.get('file')
        filename = ""
        
        if file and file.filename != "":
            filename = secure_filename(file.filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        tags = request.form.get('tags', '').strip()
        
        new_entry = {
            "username": username,
            "title": title,
            "content": content,
            "mood": mood,
            "date": date,
            "file": filename,
            "tags": tags
        }
        
        save_entry(new_entry)
        session['flash'] = 'Diary entry saved successfully.'
        # Redirect to the month of the saved entry
        entry_date = datetime.strptime(date, '%Y-%m-%d')
        return redirect(f'/?year={entry_date.year}&month={entry_date.month}')
    
    # if a date is passed in via the calendar selection, use it as the default
    date_default = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    return render_template('add.html', date_default=date_default)


# 👤 Profile page - stats and analytics
@app.route('/profile')
def profile():
    print(f"profile called, logged_in: {session.get('logged_in')}, username: {session.get('username')}")
    if not session.get('logged_in'):
        return redirect('/login')
    
    username = session.get('username')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT full_name, email, bio, profile_pic, joined_date FROM users WHERE username = ?', (username,))
    row = c.fetchone()
    
    if row:
        user_data = {
            'full_name': row[0],
            'email': row[1],
            'bio': row[2],
            'profile_pic': row[3],
            'joined_date': row[4]
        }
        print(f"Profile data: {user_data}")
    else:
        # User deleted from DB but still in session
        conn.close()
        session.clear()
        flash('Session expired. Please log in again.', 'warning')
        return redirect('/login')
        
    conn.close()
    entries = get_user_entries(username)
    
    total_entries = len(entries)
    
    if total_entries == 0:
        return render_template('profile.html', 
                             user_data=user_data,
                             total_entries=0, 
                             most_frequent_mood=None, 
                             mood_counts={})
    
    moods = [entry['mood'] for entry in entries]
    mood_counts = dict(Counter(moods))
    most_frequent_mood = max(mood_counts, key=mood_counts.get) if mood_counts else None
    
    return render_template('profile.html', 
                         user_data=user_data,
                         total_entries=total_entries,
                         most_frequent_mood=most_frequent_mood,
                         mood_counts=mood_counts,
                         entries=entries)


# 🔐 Login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        
        if username in users and check_password_hash(users[username]['password'], password):
            session['logged_in'] = True
            session['username'] = username
            session.permanent = True
            return redirect('/')
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')


# 📝 Signup page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        bio = request.form.get('bio', '')
        
        users = load_users()
        
        # Validation
        if username in users:
            return render_template('signup.html', error='Username already exists')
        
        if len(username) < 3:
            return render_template('signup.html', error='Username must be at least 3 characters')
        
        if password != confirm_password:
            return render_template('signup.html', error='Passwords do not match')
        
        if len(password) < 4:
            return render_template('signup.html', error='Password must be at least 4 characters')
        
        # Create user
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('INSERT INTO users (username, password, full_name, email, bio, joined_date) VALUES (?, ?, ?, ?, ?, ?)',
                  (username, generate_password_hash(password), full_name, email, bio, datetime.now().strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()
        
        # Auto login
        session['logged_in'] = True
        session['username'] = username
        session.permanent = True
        
        return redirect('/')
    
    return render_template('signup.html')


# 🚪 Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


init_db()

if __name__ == "__main__":
    app.run(debug=True)