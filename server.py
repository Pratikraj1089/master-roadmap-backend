#!/usr/bin/env python3
import http.server
import socketserver
import socket
import json
import sqlite3
import hashlib
import secrets
import os
import urllib.parse
import base64
import time
import re
from datetime import datetime

PORT = int(os.environ.get("PORT", 5000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "roadmap.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = hashlib.sha256("admin123".encode('utf-8')).hexdigest()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            token TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # Seed default admin user
    cursor.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,))
    if not cursor.fetchone():
        admin_token = secrets.token_hex(32)
        cursor.execute(
            "INSERT INTO users (username, password_hash, token, is_admin) VALUES (?, ?, ?, 1)",
            (ADMIN_USERNAME, ADMIN_PASSWORD_HASH, admin_token)
        )
    
    # 2. Create user_progress table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_progress (
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, item_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # 3. Create section_playlists table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS section_playlists (
            section_id TEXT PRIMARY KEY,
            banner_title TEXT NOT NULL,
            playlist_name TEXT NOT NULL,
            playlist_url TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute("SELECT COUNT(*) FROM section_playlists")
    if cursor.fetchone()[0] == 0:
        default_playlists = [
            ("aiml", "🤖 Complete AI / ML & Python Playlist:", "▶ Watch Krish Naik Complete AI/ML Playlist on YouTube", "https://www.youtube.com/watch?v=kqtD5dpn9C8"),
            ("backend", "⚡ Complete Smariously Backend Playlist:", "▶ Watch Smariously Backend Playlist on YouTube", "https://youtube.com/playlist?list=PLui3EUkuMTPgZcV0QhQrOcwMPcBCcd_Q1&si=8RpkhC8gILU0X3G6"),
            ("sql", "🗄️ Complete SQL & Databases Playlist:", "▶ Watch techTFQ SQL Playlist on YouTube", "https://www.youtube.com/watch?v=OWX4p5oSowg"),
            ("webdev", "🎨 Complete Web Development Playlist:", "▶ Watch Namaste JavaScript & Chai aur Code Playlist on YouTube", "https://www.youtube.com/watch?v=3bgS6m4H3vY"),
            ("cloud", "☁️ Complete AWS Cloud & DevOps Playlist:", "▶ Watch Abhishek Veeramalla AWS Playlist on YouTube", "https://www.youtube.com/watch?v=rKNSc8RrwxA&list=PL6XT0grm_TfgtwtwUit305qS-HhDvb4du"),
            ("dbms", "🗄️ Complete DBMS & Database Engineering Playlist:", "▶ Watch Gate Smashers Complete DBMS Playlist on YouTube", "https://www.youtube.com/playlist?list=PLxCzCOWd7aiFAN6I8CuViBuCdJgiOkT2Y"),
            ("sysdesign", "🏗️ Complete System Design Master Playlist:", "▶ Watch Gaurav Sen Complete System Design Playlist on YouTube", "https://www.youtube.com/playlist?list=PLMCXHnjXnTnvo6alSjV4gCQfIBaRHfaUU")
        ]
        cursor.executemany("INSERT OR IGNORE INTO section_playlists (section_id, banner_title, playlist_name, playlist_url) VALUES (?, ?, ?, ?)", default_playlists)

    # 4. Create section_notes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS section_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            note_title TEXT NOT NULL,
            description TEXT,
            file_url TEXT NOT NULL,
            is_pdf INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    default_notes = [
        ("aiml", "🐍 Python & Data Science Master PDF CheatSheet", "Comprehensive reference PDF covering Python Data Structures, NumPy, Pandas & ML Algorithms.", "/uploads/python_aiml_master_notes.pdf", 1),
        ("backend", "⚡ Backend Architecture, HTTP & System Design Notes", "Detailed notes on HTTP/2, RESTful URI Design, Database Indexing, Caching & Microservices.", "/uploads/backend_architecture_notes.pdf", 1),
        ("sql", "🗄️ PostgreSQL & Advanced SQL Window Functions PDF Guide", "Complete guide for Joins, Subqueries, CTEs, Window Functions & Postgres Tuning.", "/uploads/sql_databases_notes.pdf", 1),
        ("webdev", "🎨 Modern HTML5, CSS Grid & JavaScript ES6+ Study Notes", "Quick reference notes for CSS Flexbox, Grid, Execution Context, Closures & Promises.", "/uploads/web_development_notes.pdf", 1),
        ("cloud", "☁️ AWS Cloud & DevOps Infrastructure Master PDF Guide", "Comprehensive guide covering AWS EC2, S3, IAM, VPC, Lambda, ECS Containers & CloudWatch.", "/uploads/aws_cloud_devops_notes.pdf", 1),
        ("dbms", "🗄️ Database Systems & SQL Master PDF Guide", "Complete guide covering Relational Model, ER Diagrams, Normalization (1NF-BCNF), Indexing & Transactions.", "/uploads/dbms_engineering_notes.pdf", 1),
        ("sysdesign", "🏗️ System Design & Architecture Primer Notes", "Comprehensive reference notes on Scalability, Load Balancing, Caching, Messaging Queues & Microservices.", "/uploads/system_design_primer_notes.pdf", 1)
    ]
    for n in default_notes:
        cursor.execute("SELECT id FROM section_notes WHERE section_id = ?", (n[0],))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO section_notes (section_id, note_title, description, file_url, is_pdf) VALUES (?, ?, ?, ?, ?)", n)
        else:
            cursor.execute("UPDATE section_notes SET note_title = ?, description = ?, file_url = ?, is_pdf = ? WHERE section_id = ?", (n[1], n[2], n[3], n[4], n[0]))
    
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_user_by_token(token: str):
    if not token:
        return None
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, is_admin FROM users WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "username": row[1], "is_admin": bool(row[2])}
    return None

class RoadmapRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def get_auth_token(self):
        auth_header = self.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            return auth_header.split(' ', 1)[1]
        return None

    def send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == '/api/me':
            token = self.get_auth_token()
            user = get_user_by_token(token)
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            return self.send_json({"status": "success", "user": user})

        elif path == '/api/progress':
            token = self.get_auth_token()
            user = get_user_by_token(token)
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT item_id, completed FROM user_progress WHERE user_id = ?", (user["id"],))
            rows = cursor.fetchall()
            conn.close()

            progress = {row[0]: bool(row[1]) for row in rows}
            return self.send_json({"status": "success", "progress": progress})

        elif path == '/api/resources':
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            # Fetch playlists
            cursor.execute("SELECT section_id, banner_title, playlist_name, playlist_url FROM section_playlists")
            pl_rows = cursor.fetchall()
            playlists = {r[0]: {"banner_title": r[1], "playlist_name": r[2], "playlist_url": r[3]} for r in pl_rows}

            # Fetch notes
            cursor.execute("SELECT id, section_id, note_title, description, file_url, is_pdf, created_at FROM section_notes ORDER BY id DESC")
            note_rows = cursor.fetchall()
            conn.close()

            notes = [{
                "id": r[0],
                "section_id": r[1],
                "note_title": r[2],
                "description": r[3],
                "file_url": r[4],
                "is_pdf": bool(r[5]),
                "created_at": r[6]
            } for r in note_rows]

            return self.send_json({"status": "success", "playlists": playlists, "notes": notes})

        elif path == '/api/admin/users':
            token = self.get_auth_token()
            user = get_user_by_token(token)
            if not user or not user.get("is_admin"):
                return self.send_json({"error": "Admin authorization required"}, 403)

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, is_admin, created_at FROM users ORDER BY id DESC")
            rows = cursor.fetchall()
            conn.close()

            users_list = [{
                "id": r[0],
                "username": r[1],
                "is_admin": bool(r[2]),
                "created_at": r[3]
            } for r in rows]

            return self.send_json({"status": "success", "total_users": len(users_list), "users": users_list})

        else:
            if path == '/' or path == '':
                self.path = '/index.html'
            try:
                return super().do_GET()
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get('Content-Length', 0))
        body_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
        try:
            payload = json.loads(body_data.decode('utf-8'))
        except json.JSONDecodeError:
            payload = {}

        if path == '/api/register':
            username = payload.get('username', '').strip()
            password = payload.get('password', '').strip()

            if not username or not password:
                return self.send_json({"error": "Username and password are required."}, 400)
            if len(username) < 3:
                return self.send_json({"error": "Username must be at least 3 characters."}, 400)

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            try:
                pass_hash = hash_password(password)
                token = secrets.token_hex(32)
                is_admin = 1 if username.lower() == ADMIN_USERNAME else 0
                cursor.execute(
                    "INSERT INTO users (username, password_hash, token, is_admin) VALUES (?, ?, ?, ?)",
                    (username, pass_hash, token, is_admin)
                )
                conn.commit()
                conn.close()
                return self.send_json({
                    "status": "success",
                    "message": "User registered successfully!",
                    "token": token,
                    "username": username,
                    "is_admin": bool(is_admin)
                })
            except sqlite3.IntegrityError:
                conn.close()
                return self.send_json({"error": "Username already exists. Please login instead."}, 400)

        elif path == '/api/login':
            username = payload.get('username', '').strip()
            password = payload.get('password', '').strip()

            if not username or not password:
                return self.send_json({"error": "Username and password are required."}, 400)

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            pass_hash = hash_password(password)
            cursor.execute(
                "SELECT id, username, is_admin FROM users WHERE LOWER(username) = LOWER(?) AND password_hash = ?",
                (username, pass_hash)
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return self.send_json({"error": "Invalid username or password."}, 401)

            user_id, uname, is_admin = row[0], row[1], row[2]
            token = secrets.token_hex(32)
            cursor.execute("UPDATE users SET token = ? WHERE id = ?", (token, user_id))
            conn.commit()
            conn.close()

            return self.send_json({
                "status": "success",
                "message": "Logged in successfully!",
                "token": token,
                "username": uname,
                "is_admin": bool(is_admin)
            })

        elif path == '/api/progress/toggle':
            token = self.get_auth_token()
            user = get_user_by_token(token)
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)

            item_id = payload.get('item_id')
            completed = 1 if payload.get('completed') else 0

            if not item_id:
                return self.send_json({"error": "item_id is required"}, 400)

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_progress (user_id, item_id, completed, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, item_id) DO UPDATE SET
                    completed = excluded.completed,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user["id"], item_id, completed))
            conn.commit()
            conn.close()

            return self.send_json({"status": "success", "item_id": item_id, "completed": bool(completed)})

        elif path == '/api/admin/playlist':
            token = self.get_auth_token()
            user = get_user_by_token(token)
            if not user or not user.get("is_admin"):
                return self.send_json({"error": "Admin authorization required"}, 403)

            section_id = payload.get('section_id')
            banner_title = payload.get('banner_title', '').strip()
            playlist_name = payload.get('playlist_name', '').strip()
            playlist_url = payload.get('playlist_url', '').strip()

            if not section_id or not playlist_url:
                return self.send_json({"error": "section_id and playlist_url are required"}, 400)

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO section_playlists (section_id, banner_title, playlist_name, playlist_url, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(section_id) DO UPDATE SET
                    banner_title = excluded.banner_title,
                    playlist_name = excluded.playlist_name,
                    playlist_url = excluded.playlist_url,
                    updated_at = CURRENT_TIMESTAMP
            ''', (section_id, banner_title, playlist_name, playlist_url))
            conn.commit()
            conn.close()

            return self.send_json({"status": "success", "message": f"Updated playlist link for section '{section_id}'"})

        elif path == '/api/admin/notes/add':
            token = self.get_auth_token()
            user = get_user_by_token(token)
            if not user or not user.get("is_admin"):
                return self.send_json({"error": "Admin authorization required"}, 403)

            section_id = payload.get('section_id')
            note_title = payload.get('note_title', '').strip()
            description = payload.get('description', '').strip()
            file_url = payload.get('file_url', '').strip()
            file_base64 = payload.get('file_base64', '').strip()
            file_name = payload.get('file_name', '').strip()
            is_pdf = 1 if payload.get('is_pdf', True) else 0

            if not section_id or not note_title:
                return self.send_json({"error": "section_id and note_title are required"}, 400)

            # Save base64 local file upload if provided
            if file_base64 and file_name:
                try:
                    if ',' in file_base64:
                        file_base64 = file_base64.split(',', 1)[1]
                    file_bytes = base64.b64decode(file_base64)
                    clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', file_name)
                    saved_filename = f"{int(time.time())}_{clean_name}"
                    file_path = os.path.join(UPLOADS_DIR, saved_filename)
                    with open(file_path, 'wb') as f:
                        f.write(file_bytes)
                    file_url = f"/uploads/{saved_filename}"
                except Exception as e:
                    return self.send_json({"error": f"Failed to save uploaded file: {str(e)}"}, 500)

            if not file_url:
                return self.send_json({"error": "Either external file_url or local file upload is required"}, 400)

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO section_notes (section_id, note_title, description, file_url, is_pdf) VALUES (?, ?, ?, ?, ?)",
                (section_id, note_title, description, file_url, is_pdf)
            )
            note_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return self.send_json({"status": "success", "message": "Added new note successfully!", "note_id": note_id, "file_url": file_url})

        elif path == '/api/admin/notes/delete':
            token = self.get_auth_token()
            user = get_user_by_token(token)
            if not user or not user.get("is_admin"):
                return self.send_json({"error": "Admin authorization required"}, 403)

            note_id = payload.get('note_id')
            if not note_id:
                return self.send_json({"error": "note_id is required"}, 400)

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM section_notes WHERE id = ?", (note_id,))
            conn.commit()
            conn.close()

            return self.send_json({"status": "success", "message": f"Deleted note #{note_id}"})

        elif path == '/api/admin/user/reset-password':
            token = self.get_auth_token()
            user = get_user_by_token(token)
            if not user or not user.get("is_admin"):
                return self.send_json({"error": "Admin authorization required"}, 403)

            target_user_id = payload.get('user_id')
            new_password = payload.get('new_password', '').strip()

            if not target_user_id or not new_password:
                return self.send_json({"error": "user_id and new_password are required"}, 400)
            if len(new_password) < 4:
                return self.send_json({"error": "New password must be at least 4 characters"}, 400)

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE id = ?", (target_user_id,))
            target_user = cursor.fetchone()
            if not target_user:
                conn.close()
                return self.send_json({"error": "User not found"}, 404)

            new_hash = hash_password(new_password)
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, target_user_id))
            conn.commit()
            conn.close()

            return self.send_json({
                "status": "success",
                "message": f"Password for user '{target_user[0]}' updated successfully!"
            })

        else:
            return self.send_json({"error": "Route not found"}, 404)

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception:
            pass
        super().server_bind()

if __name__ == '__main__':
    init_db()
    server = None
    for attempt in range(10):
        try:
            server = ReusableTCPServer(("0.0.0.0", PORT), RoadmapRequestHandler)
            print(f"🚀 Master Roadmap Backend Server running at http://0.0.0.0:{PORT}")
            break
        except OSError:
            import time
            time.sleep(1)
    
    if not server:
        for port in range(PORT + 1, PORT + 10):
            try:
                server = ReusableTCPServer(("0.0.0.0", port), RoadmapRequestHandler)
                PORT = port
                print(f"🚀 Master Roadmap Backend Server running at http://0.0.0.0:{PORT}")
                break
            except OSError:
                continue

    if server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            server.server_close()
