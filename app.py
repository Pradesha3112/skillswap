from flask import Flask, render_template, session, redirect, url_for, request, flash, get_flashed_messages, jsonify
from functools import wraps
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

DATABASE = 'skillswap.db'

# Database initialization
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Create users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Migrate users table - add new columns if they don't exist
    try:
        c.execute('ALTER TABLE users ADD COLUMN profile_summary TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN badge_level INTEGER DEFAULT 1')
        # Update existing rows to have default badge_level
        c.execute('UPDATE users SET badge_level = 1 WHERE badge_level IS NULL')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN language TEXT DEFAULT "en"')
        c.execute('UPDATE users SET language = "en" WHERE language IS NULL')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN font_size TEXT DEFAULT "medium"')
        c.execute('UPDATE users SET font_size = "medium" WHERE font_size IS NULL')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN theme TEXT DEFAULT "light"')
        c.execute('UPDATE users SET theme = "light" WHERE theme IS NULL')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
        c.execute('UPDATE users SET is_admin = 0 WHERE is_admin IS NULL')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Create skills table
    c.execute('''CREATE TABLE IF NOT EXISTS skills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        skill_offered TEXT NOT NULL,
        skill_wanted TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    
    # Create messages table
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        skill_post_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sender_id) REFERENCES users(id),
        FOREIGN KEY (receiver_id) REFERENCES users(id),
        FOREIGN KEY (skill_post_id) REFERENCES skills(id)
    )''')
    
    # Create notifications table
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        message_id INTEGER,
        skill_post_id INTEGER,
        notification_type TEXT DEFAULT 'message',
        message_preview TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (sender_id) REFERENCES users(id),
        FOREIGN KEY (message_id) REFERENCES messages(id),
        FOREIGN KEY (skill_post_id) REFERENCES skills(id)
    )''')
    
    # Create ratings table
    c.execute('''CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rated_user_id INTEGER NOT NULL,
        rater_user_id INTEGER NOT NULL,
        skill_post_id INTEGER,
        rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (rated_user_id) REFERENCES users(id),
        FOREIGN KEY (rater_user_id) REFERENCES users(id),
        FOREIGN KEY (skill_post_id) REFERENCES skills(id),
        UNIQUE(rated_user_id, rater_user_id, skill_post_id)
    )''')
    
    # Create bookmarks table
    c.execute('''CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        skill_post_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (skill_post_id) REFERENCES skills(id),
        UNIQUE(user_id, skill_post_id)
    )''')
    
    conn.commit()
    conn.close()

# Database helper functions
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COALESCE(is_admin, 0) as is_admin FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        conn.close()
        if not user or not user['is_admin']:
            flash('Admin access required', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def get_unread_notification_count(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND is_read = 0', (user_id,))
    result = c.fetchone()
    conn.close()
    return result['count'] if result else 0

def create_notification(user_id, sender_id, message_id, skill_post_id, message_preview):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO notifications (user_id, sender_id, message_id, skill_post_id, message_preview)
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, sender_id, message_id, skill_post_id, message_preview[:100]))
    conn.commit()
    conn.close()

def calculate_badge_level(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT AVG(rating) as avg_rating FROM ratings WHERE rated_user_id = ?', (user_id,))
    result = c.fetchone()
    avg_rating = result['avg_rating'] if result and result['avg_rating'] else 0
    
    if avg_rating >= 4.5:
        badge_level = 10
    elif avg_rating >= 4.0:
        badge_level = 9
    elif avg_rating >= 3.5:
        badge_level = 8
    elif avg_rating >= 3.0:
        badge_level = 7
    elif avg_rating >= 2.5:
        badge_level = 6
    elif avg_rating >= 2.0:
        badge_level = 5
    elif avg_rating >= 1.5:
        badge_level = 4
    elif avg_rating >= 1.0:
        badge_level = 3
    elif avg_rating > 0:
        badge_level = 2
    else:
        badge_level = 1
    
    c.execute('UPDATE users SET badge_level = ? WHERE id = ?', (badge_level, user_id))
    conn.commit()
    conn.close()
    return badge_level

def calculate_profile_strength(user_id):
    conn = get_db()
    c = conn.cursor()
    
    # Get user data
    c.execute('SELECT profile_summary FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    has_summary = bool(user and user['profile_summary'])
    
    c.execute('SELECT COUNT(*) as count FROM skills WHERE user_id = ?', (user_id,))
    posts_count = c.fetchone()['count']
    
    c.execute('SELECT COALESCE(badge_level, 1) as badge_level FROM users WHERE id = ?', (user_id,))
    result = c.fetchone()
    badge_level = result['badge_level'] if result else 1
    
    conn.close()
    
    # Calculate strength (0-100)
    score = 0
    if has_summary:
        score += 25
    if posts_count > 0:
        score += min(25, posts_count * 5)  # Max 25 points for posts
    score += min(50, badge_level * 5)  # Max 50 points for badges
    
    return min(100, score)

# Context processor to make notification_count available globally
@app.context_processor
def inject_notification_count():
    if 'user_id' in session:
        return {'notification_count': get_unread_notification_count(session['user_id'])}
    return {'notification_count': 0}

# Translation dictionary (simplified i18n)
TRANSLATIONS = {
    'en': {
        'home': 'Home',
        'community': 'Community',
        'profile': 'Profile',
        'notifications': 'Notifications',
        'logout': 'Logout',
        'welcome': 'Welcome',
        'create_post': 'Create Post',
        'explore_community': 'Explore Community',
    },
    'es': {
        'home': 'Inicio',
        'community': 'Comunidad',
        'profile': 'Perfil',
        'notifications': 'Notificaciones',
        'logout': 'Cerrar sesión',
        'welcome': 'Bienvenido',
        'create_post': 'Crear Publicación',
        'explore_community': 'Explorar Comunidad',
    },
    'fr': {
        'home': 'Accueil',
        'community': 'Communauté',
        'profile': 'Profil',
        'notifications': 'Notifications',
        'logout': 'Déconnexion',
        'welcome': 'Bienvenue',
        'create_post': 'Créer une publication',
        'explore_community': 'Explorer la communauté',
    },
    'de': {
        'home': 'Startseite',
        'community': 'Gemeinschaft',
        'profile': 'Profil',
        'notifications': 'Benachrichtigungen',
        'logout': 'Abmelden',
        'welcome': 'Willkommen',
        'create_post': 'Beitrag erstellen',
        'explore_community': 'Gemeinschaft erkunden',
    },
    'hi': {
        'home': 'होम',
        'community': 'समुदाय',
        'profile': 'प्रोफ़ाइल',
        'notifications': 'सूचनाएं',
        'logout': 'लॉगआउट',
        'welcome': 'स्वागत है',
        'create_post': 'पोस्ट बनाएं',
        'explore_community': 'समुदाय देखें',
    }
}

@app.route('/')
def index():
    # Show public home page
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    # Renamed from 'home' to 'dashboard' for logged-in users
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT username FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    notification_count = get_unread_notification_count(session['user_id'])
    
    return render_template('home.html', 
                         username=user['username'] if user else session.get('username', 'User'),
                         notification_count=notification_count)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not username or not email or not password or not confirm_password:
            flash('All fields are required', 'error')
            return render_template('signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('signup.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template('signup.html')
        
        conn = get_db()
        c = conn.cursor()
        
        # Check if username exists
        c.execute('SELECT id FROM users WHERE username = ?', (username,))
        if c.fetchone():
            flash('Username already exists', 'error')
            conn.close()
            return render_template('signup.html')
        
        # Check if email exists
        c.execute('SELECT id FROM users WHERE email = ?', (email,))
        if c.fetchone():
            flash('Email already exists', 'error')
            conn.close()
            return render_template('signup.html')
        
        # Create user
        hashed_password = generate_password_hash(password)
        c.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                  (username, email, hashed_password))
        conn.commit()
        conn.close()
        
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username_or_email or not password:
            flash('Username/Email and password are required', 'error')
            return render_template('login.html')
        
        conn = get_db()
        c = conn.cursor()
        
        # Check by username or email
        c.execute('SELECT * FROM users WHERE username = ? OR email = ?',
                  (username_or_email, username_or_email))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            # Handle new columns that might not exist in old databases
            try:
                session['language'] = user['language'] if user['language'] else 'en'
            except (KeyError, IndexError):
                session['language'] = 'en'
            try:
                session['is_admin'] = user['is_admin'] if user['is_admin'] is not None else 0
            except (KeyError, IndexError):
                session['is_admin'] = 0
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username/email or password', 'error')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT username FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    notification_count = get_unread_notification_count(session['user_id'])
    
    return render_template('home.html', 
                         username=user['username'] if user else session.get('username', 'User'),
                         notification_count=notification_count)

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        skill_offered = request.form.get('skill_offered', '').strip()
        skill_wanted = request.form.get('skill_wanted', '').strip()
        description = request.form.get('description', '').strip()
        
        if not skill_offered or not skill_wanted:
            flash('Both "Skill Offered" and "Skill Wanted" are required', 'error')
            return render_template('create_post.html')
        
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO skills (user_id, skill_offered, skill_wanted, description)
                     VALUES (?, ?, ?, ?)''',
                  (session['user_id'], skill_offered, skill_wanted, description))
        conn.commit()
        conn.close()
        
        flash('Post created successfully!', 'success')
        return redirect(url_for('community'))
    
    notification_count = get_unread_notification_count(session['user_id'])
    return render_template('create_post.html', notification_count=notification_count)

@app.route('/community')
@login_required
def community():
    search = request.args.get('search', '').strip()
    skill_offered = request.args.get('skill_offered', '').strip()
    skill_wanted = request.args.get('skill_wanted', '').strip()
    min_badge = request.args.get('min_badge', '')
    min_rating = request.args.get('min_rating', '')
    
    conn = get_db()
    c = conn.cursor()
    
    query = '''SELECT s.*, u.username, COALESCE(u.badge_level, 1) as badge_level,
               COALESCE(AVG(r.rating), 0) as avg_rating
               FROM skills s 
               JOIN users u ON s.user_id = u.id 
               LEFT JOIN ratings r ON r.rated_user_id = u.id'''
    
    conditions = []
    params = []
    
    if search:
        conditions.append('(s.skill_offered LIKE ? OR s.skill_wanted LIKE ? OR s.description LIKE ?)')
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    
    if skill_offered:
        conditions.append('s.skill_offered LIKE ?')
        params.append(f'%{skill_offered}%')
    
    if skill_wanted:
        conditions.append('s.skill_wanted LIKE ?')
        params.append(f'%{skill_wanted}%')
    
    if min_badge:
        conditions.append('COALESCE(u.badge_level, 1) >= ?')
        params.append(int(min_badge))
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    
    query += ' GROUP BY s.id, u.id ORDER BY s.created_at DESC'
    
    c.execute(query, params)
    posts = c.fetchall()
    
    # Check which posts are bookmarked
    c.execute('SELECT skill_post_id FROM bookmarks WHERE user_id = ?', (session['user_id'],))
    bookmarked_ids = [row['skill_post_id'] for row in c.fetchall()]
    
    conn.close()
    
    notification_count = get_unread_notification_count(session['user_id'])
    
    return render_template('community.html', 
                         posts=posts, 
                         search=search,
                         skill_offered=skill_offered,
                         skill_wanted=skill_wanted,
                         min_badge=min_badge,
                         min_rating=min_rating,
                         bookmarked_ids=bookmarked_ids,
                         notification_count=notification_count)

@app.route('/message/<int:post_id>', methods=['GET', 'POST'])
@login_required
def message(post_id):
    conn = get_db()
    c = conn.cursor()
    
    # Get post details
    c.execute('''SELECT s.*, u.username, u.id as user_id
                 FROM skills s 
                 JOIN users u ON s.user_id = u.id 
                 WHERE s.id = ?''', (post_id,))
    post = c.fetchone()
    
    if not post:
        flash('Post not found', 'error')
        conn.close()
        return redirect(url_for('community'))
    
    # Handle message sending
    if request.method == 'POST':
        message_text = request.form.get('message', '').strip()
        if message_text:
            receiver_id = post['user_id']
            c.execute('''INSERT INTO messages (sender_id, receiver_id, skill_post_id, message)
                         VALUES (?, ?, ?, ?)''',
                      (session['user_id'], receiver_id, post_id, message_text))
            message_id = c.lastrowid
            conn.commit()
            
            # Create notification for receiver
            create_notification(receiver_id, session['user_id'], message_id, post_id, message_text)
            
            # Create notification for sender (so they can see their sent messages)
            create_notification(session['user_id'], session['user_id'], message_id, post_id, f"You sent: {message_text[:50]}")
            
            flash('Message sent!', 'success')
    
    # Get all messages for this post
    c.execute('''SELECT m.*, u1.username as sender_name, u2.username as receiver_name
                 FROM messages m
                 JOIN users u1 ON m.sender_id = u1.id
                 JOIN users u2 ON m.receiver_id = u2.id
                 WHERE m.skill_post_id = ?
                 ORDER BY m.sent_at ASC''', (post_id,))
    messages = c.fetchall()
    
    conn.close()
    
    notification_count = get_unread_notification_count(session['user_id'])
    
    return render_template('message.html', post=post, messages=messages, notification_count=notification_count)

@app.route('/notifications')
@login_required
def notifications():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''SELECT n.*, u.username as sender_name, n.sender_id, n.user_id
                 FROM notifications n
                 JOIN users u ON n.sender_id = u.id
                 WHERE n.user_id = ?
                 ORDER BY n.created_at DESC''', (session['user_id'],))
    notifications_list = c.fetchall()
    
    conn.close()
    
    notification_count = get_unread_notification_count(session['user_id'])
    
    return render_template('notifications.html', 
                         notifications=notifications_list,
                         notification_count=notification_count)

@app.route('/mark_notification_read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
              (notification_id, session['user_id']))
    conn.commit()
    conn.close()
    
    # Always return JSON response
    return jsonify({'success': True})

@app.route('/rate_user/<int:user_id>/<int:post_id>', methods=['POST'])
@login_required
def rate_user(user_id, post_id):
    rating = int(request.form.get('rating', 0))
    comment = request.form.get('comment', '').strip()
    
    if rating < 1 or rating > 5:
        flash('Invalid rating', 'error')
        return redirect(url_for('message', post_id=post_id))
    
    conn = get_db()
    c = conn.cursor()
    
    # Check if already rated
    c.execute('SELECT id FROM ratings WHERE rated_user_id = ? AND rater_user_id = ? AND skill_post_id = ?',
              (user_id, session['user_id'], post_id))
    if c.fetchone():
        c.execute('UPDATE ratings SET rating = ?, comment = ? WHERE rated_user_id = ? AND rater_user_id = ? AND skill_post_id = ?',
                  (rating, comment, user_id, session['user_id'], post_id))
    else:
        c.execute('INSERT INTO ratings (rated_user_id, rater_user_id, skill_post_id, rating, comment) VALUES (?, ?, ?, ?, ?)',
                 (user_id, session['user_id'], post_id, rating, comment))
    
    conn.commit()
    
    # Recalculate badge level
    calculate_badge_level(user_id)
    
    conn.close()
    flash('Rating submitted!', 'success')
    return redirect(url_for('message', post_id=post_id))

@app.route('/bookmark/<int:post_id>', methods=['POST'])
@login_required
def bookmark(post_id):
    conn = get_db()
    c = conn.cursor()
    
    # Check if already bookmarked
    c.execute('SELECT id FROM bookmarks WHERE user_id = ? AND skill_post_id = ?',
              (session['user_id'], post_id))
    if c.fetchone():
        c.execute('DELETE FROM bookmarks WHERE user_id = ? AND skill_post_id = ?',
                  (session['user_id'], post_id))
        action = 'removed'
    else:
        c.execute('INSERT INTO bookmarks (user_id, skill_post_id) VALUES (?, ?)',
                  (session['user_id'], post_id))
        action = 'added'
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'action': action})

@app.route('/profile')
@login_required
def profile():
    conn = get_db()
    c = conn.cursor()
    
    # Get user details
    c.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    
    # Get user's posts
    c.execute('''SELECT * FROM skills 
                 WHERE user_id = ? 
                 ORDER BY created_at DESC''', (session['user_id'],))
    posts = c.fetchall()
    
    # Get notifications
    c.execute('''SELECT n.*, u.username as sender_name
                 FROM notifications n
                 JOIN users u ON n.sender_id = u.id
                 WHERE n.user_id = ?
                 ORDER BY n.created_at DESC
                 LIMIT 10''', (session['user_id'],))
    notifications_list = c.fetchall()
    
    # Get bookmarked posts
    c.execute('''SELECT s.*, u.username
                 FROM bookmarks b
                 JOIN skills s ON b.skill_post_id = s.id
                 JOIN users u ON s.user_id = u.id
                 WHERE b.user_id = ?
                 ORDER BY b.created_at DESC''', (session['user_id'],))
    bookmarked_posts = c.fetchall()
    
    # Get ratings received
    c.execute('''SELECT AVG(rating) as avg_rating, COUNT(*) as rating_count
                 FROM ratings WHERE rated_user_id = ?''', (session['user_id'],))
    rating_data = c.fetchone()
    
    # Handle badge_level that might not exist
    try:
        badge_level = user['badge_level'] if user['badge_level'] is not None else 1
    except (KeyError, IndexError):
        badge_level = 1
    profile_strength = calculate_profile_strength(session['user_id'])
    
    conn.close()
    
    notification_count = get_unread_notification_count(session['user_id'])
    
    return render_template('profile.html', 
                         user=user, 
                         posts=posts,
                         notifications=notifications_list,
                         bookmarked_posts=bookmarked_posts,
                         badge_level=badge_level,
                         profile_strength=profile_strength,
                         avg_rating=rating_data['avg_rating'] if rating_data['avg_rating'] else 0,
                         rating_count=rating_data['rating_count'] or 0,
                         notification_count=notification_count)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    profile_summary = request.form.get('profile_summary', '').strip()
    language = request.form.get('language', 'en')
    font_size = request.form.get('font_size', 'medium')
    theme = request.form.get('theme', 'light')
    
    conn = get_db()
    c = conn.cursor()
    
    # Update only provided fields
    if profile_summary:
        c.execute('UPDATE users SET profile_summary = ? WHERE id = ?',
                  (profile_summary, session['user_id']))
    
    if language:
        c.execute('UPDATE users SET language = ? WHERE id = ?',
                  (language, session['user_id']))
        session['language'] = language
    
    if font_size:
        c.execute('UPDATE users SET font_size = ? WHERE id = ?',
                  (font_size, session['user_id']))
    
    if theme:
        c.execute('UPDATE users SET theme = ? WHERE id = ?',
                  (theme, session['user_id']))
    
    conn.commit()
    conn.close()
    
    # Check if this is an AJAX request (settings form)
    if request.headers.get('Content-Type') and 'application/x-www-form-urlencoded' in request.headers.get('Content-Type', ''):
        return jsonify({'success': True, 'message': 'Settings saved successfully!'})
    
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    conn = get_db()
    c = conn.cursor()
    
    # Total users
    c.execute('SELECT COUNT(*) as count FROM users')
    total_users = c.fetchone()['count']
    
    # Total posts
    c.execute('SELECT COUNT(*) as count FROM skills')
    total_posts = c.fetchone()['count']
    
    # Messages sent
    c.execute('SELECT COUNT(*) as count FROM messages')
    messages_sent = c.fetchone()['count']
    
    # Active users (users who logged in within last 30 days - simplified as users with posts)
    c.execute('''SELECT COUNT(DISTINCT user_id) as count 
                 FROM skills 
                 WHERE created_at >= datetime('now', '-30 days')''')
    active_users = c.fetchone()['count']
    
    conn.close()
    
    notification_count = get_unread_notification_count(session['user_id'])
    
    return render_template('admin_analytics.html',
                         total_users=total_users,
                         total_posts=total_posts,
                         messages_sent=messages_sent,
                         active_users=active_users,
                         notification_count=notification_count)

@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    conn = get_db()
    c = conn.cursor()
    
    # Verify post belongs to user
    c.execute('SELECT user_id FROM skills WHERE id = ?', (post_id,))
    post = c.fetchone()
    
    if post and post['user_id'] == session['user_id']:
        c.execute('DELETE FROM skills WHERE id = ?', (post_id,))
        conn.commit()
        flash('Post deleted successfully', 'success')
    else:
        flash('You can only delete your own posts', 'error')
    
    conn.close()
    return redirect(url_for('profile'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
