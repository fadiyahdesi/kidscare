import os
import token
from random import randint
from flask_mail import Mail, Message
from datetime import timedelta
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, redirect, session, url_for, Blueprint, flash, abort
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from app.services.yt_service import get_realtime_adhd_videos
from authlib.integrations.flask_client import OAuth
from functools import wraps
from werkzeug.utils import secure_filename
# from fitur_konsultasi import consult_bp

load_dotenv()

app = Flask(__name__, template_folder='app/templates', static_folder='app/static')
app.secret_key = os.environ.get('SECRET_KEY') or 'fallback-secret-key-123'

#SET CONFIG OAUTH
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# SET CONFIG MAIL
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

# Inisialisasi mail
mail = Mail(app)

# Konfigurasi Upload Folder untuk Dokumen Psikolog
UPLOAD_FOLDER = 'app/static/uploads/documents'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.template_filter('to_wib')
def to_wib(dt):
    """Filter untuk menambahkan 7 jam pada objek datetime dari MongoDB"""
    if dt:
        return dt + timedelta(hours=7)
    return dt

# --- MONGODB ---
client = MongoClient("mongodb://localhost:27017/")
db = client["kidscare_db"]

def get_indonesian_day(date_str):
    """Konversi tanggal (YYYY-MM-DD) ke nama hari Bahasa Indonesia"""
    days_map = {
        'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
        'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
    }
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        english_day = date_obj.strftime('%A')
        return days_map.get(english_day)
    except Exception:
        return "Senin"

def format_date_id(date_str):
    """Konversi YYYY-MM-DD ke format DD MMMM YYYY (Indonesian)"""
    months_id = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        day = date_obj.day
        month = months_id[date_obj.month - 1]
        year = date_obj.year
        return f"{day} {month} {year}"
    except Exception:
        return date_str
    
def admin_required(f):
    """
    Decorator untuk memastikan hanya user dengan role 'admin' 
    yang bisa mengakses rute ini.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash("Akses ditolak! Halaman ini khusus Administrator.", "danger")
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# Definisi Blueprint
main_bp = Blueprint('main', __name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
user_bp = Blueprint('user', __name__, url_prefix='/users')
consult_bp = Blueprint('consult', __name__, url_prefix='/consultation')
psych_bp = Blueprint('psychologist', __name__, url_prefix='/psychologist')

# ==========================================
# --- MAIN ROUTES ---
# ==========================================

@main_bp.route('/')
def landing():
    return render_template('index.html')

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('username')
        password = request.form.get('password')
        user = db.users.find_one({"$or": [{"email": identifier}, {"username": identifier}]})
        
        if user and check_password_hash(user['password'], password):
            
            # --- PENGECEKAN VERIFIKASI & STATUS PSIKOLOG ---
            if user.get('role') == 'psychologist':
                # Jika is_verified bernilai False atau tidak ada
                if not user.get('is_verified', False):
                    # Ambil status saat ini untuk memberikan pesan spesifik
                    status = user.get('status', 'pending')
                    
                    if status == 'rejected':
                        flash("Login ditolak! Pendaftaran Mitra Psikolog Anda telah Ditolak oleh Admin.", "danger")
                    elif status == 'suspended':
                        flash("Login ditolak! Akun Anda sedang DITANGGUHKAN oleh Admin.", "warning")
                    else:
                        flash("Login ditolak! Akun Mitra Psikolog Anda sedang dalam proses verifikasi oleh Admin.", "warning")
                    
                    return render_template('authentications/login/login.html')
            
            # --- PENGECEKAN STATUS ORANG TUA (JIKA DI-SUSPEND ADMIN) ---
            elif user.get('role') == 'parent':
                if user.get('status') == 'suspended':
                    flash("Akses ditolak! Akun Anda telah ditangguhkan sementara karena melanggar ketentuan layanan.", "danger")
                    return render_template('authentications/login/login.html')
            # ----------------------------------------
            
            session['user_id'] = str(user['_id'])
            session['role'] = user.get('role', 'parent')
            session['name'] = user['username']
            
            # --- LOGIKA REDIRECT BERDASARKAN ROLE ---
            if session['role'] == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif session['role'] == 'psychologist':
                return redirect(url_for('psychologist.dashboard'))
            
            # Default untuk Orang Tua
            return redirect(url_for('user.index'))
            
        else:
            flash("Email atau Password salah!", "danger")
            
    return render_template('authentications/login/login.html')


@main_bp.route('/login/google')
def login_google():
    redirect_uri = url_for('main.authorize_google', _external=True)
    return google.authorize_redirect(redirect_uri)


@main_bp.route('/auth/google')
def authorize_google():
    token = google.authorize_access_token()

    resp = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
    user_info = resp.json()

    email = user_info['email']
    user = db.users.find_one({"email": email})
    
    if not user:
        # User Baru: Simpan ke DB (Default sebagai Parent)
        user_result = db.users.insert_one({
            "username": user_info.get('name'),
            "email": email,
            "password": generate_password_hash("GOOGLE_AUTH_USER"),
            "role": "parent",
            "status": "active", # Default status aktif untuk Orang Tua
            "created_at": datetime.utcnow()
        })
        user_id = user_result.inserted_id
        # Ambil data yang baru dibuat
        user_data = db.users.find_one({"_id": user_id})
        session['pending_child'] = True 
    else:
        user_id = user['_id']
        # Gunakan data user yang sudah ada
        user_data = user
        session['pending_child'] = False

    # Pastikan user_data tidak None
    if not user_data:
        flash("Terjadi kesalahan sistem saat mengambil data pengguna.", "danger")
        return redirect(url_for('main.login'))

    role = user_data.get('role', 'parent')

    # --- 1. PENGECEKAN VERIFIKASI & STATUS PSIKOLOG ---
    if role == 'psychologist':
        # Periksa apakah psikolog sudah diverifikasi atau ditolak/disuspend
        if not user_data.get('is_verified', False):
            status = user_data.get('status', 'pending')
            
            if status == 'rejected':
                flash("Login ditolak! Pendaftaran Mitra Psikolog Anda telah Ditolak oleh Admin.", "danger")
            elif status == 'suspended':
                flash("Login ditolak! Akun Anda sedang DITANGGUHKAN oleh Admin.", "warning")
            else:
                flash("Login ditolak! Akun Mitra Psikolog Anda sedang dalam proses verifikasi oleh Admin.", "warning")
                
            return redirect(url_for('main.login'))

    # --- 1.B. PENGECEKAN STATUS ORANG TUA (JIKA DI-SUSPEND ADMIN) ---
    elif role == 'parent':
        if user_data.get('status') == 'suspended':
            flash("Akses ditolak! Akun Anda telah ditangguhkan sementara karena melanggar ketentuan layanan.", "danger")
            return redirect(url_for('main.login'))

    # Jika aman, set session
    session['user_id'] = str(user_id)
    session['role'] = role
    session['name'] = user_data.get('username', user_info.get('name'))

    # --- 2. LOGIKA REDIRECT BERDASARKAN ROLE ---
    if role == 'admin':
        return redirect(url_for('admin.dashboard'))
    
    elif role == 'psychologist':
        return redirect(url_for('psychologist.dashboard'))
    
    else:
        # --- 3. KHUSUS ORANG TUA: Cek Kelengkapan Data Anak ---
        child = db.children.find_one({"parent_id": ObjectId(session['user_id'])})
        
        if not child:
            flash("Selamat datang! Silakan lengkapi profil anak Anda.", "info")
            return redirect(url_for('main.add_child_profile')) 
            
        return redirect(url_for('user.index'))

@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        parent_name = request.form.get('parent_name')
        contact = request.form.get('contact') # Ini adalah email
        password = request.form.get('password')
        address = request.form.get('address')
        child_name = request.form.get('child_name')
        child_birth = request.form.get('child_birth')
        gender = request.form.get('gender')

        if db.users.find_one({"email": contact}):
            flash("Email sudah terdaftar!", "warning")
            return redirect(url_for('main.register'))

        hashed_pw = generate_password_hash(password)
        user_result = db.users.insert_one({
            "username": parent_name, "email": contact, "password": hashed_pw,
            "address": address, "role": "parent", "created_at": datetime.utcnow()
        })
        
        birth_date = datetime.strptime(child_birth, '%Y-%m-%d') if child_birth else None
        db.children.insert_one({
            "parent_id": user_result.inserted_id, "name": child_name,
            "birth_date": birth_date, "gender": gender, "created_at": datetime.utcnow()
        })
        
        # ==========================================
        # BLOK PENGIRIMAN EMAIL NOTIFIKASI
        # ==========================================
        try:
            msg = Message(
                subject='Selamat Datang di KidsCare!',
                recipients=[contact]
            )
            
            # _external=True digunakan agar URL yang terbentuk lengkap (http://domain.com/login)
            login_link = url_for('main.login', _external=True)
            
            msg.html = f"""
            <!DOCTYPE html>
            <html>
            <body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                <div style="width: 100%; max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 24px; overflow: hidden; margin-top: 40px; margin-bottom: 40px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                    <div style="background: linear-gradient(135deg, #14b8a6, #0f766e); padding: 30px 20px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 900; letter-spacing: 1px;">KidsCare</h1>
                    </div>
                    <div style="padding: 40px 30px;">
                        <h2 style="color: #1e293b; font-size: 22px; margin-top: 0;">Halo, {parent_name}!</h2>
                        <p style="color: #64748b; font-size: 16px; line-height: 1.6;">
                            Pendaftaran akun Wali/Orang Tua Anda di sistem <strong>KidsCare</strong> telah berhasil dilakukan. Kami siap membantu Anda memantau tumbuh kembang <strong>{child_name}</strong> secara berkala.
                        </p>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{login_link}" style="display: inline-block; background-color: #14b8a6; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 12px; font-weight: bold; font-size: 14px;">Mulai Tes Skrining Sekarang</a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            mail.send(msg)
        except Exception as e:
            # Print error ke terminal untuk debugging jika email gagal
            print(f"Gagal mengirim email notifikasi: {e}")
        # ==========================================

        flash("Registrasi Berhasil! Silakan cek email Anda dan Login.", "success")
        
        # Uncomment baris ini agar form benar-benar berpindah ke halaman login setelah submit
        return redirect(url_for('main.login'))
        
    return render_template('authentications/register/register.html')

@main_bp.route('/register', methods=['GET', 'POST'])
@main_bp.route('/register/psychologist', methods=['GET', 'POST'])
def register_psychologist():
    if request.method == 'POST':
        # --- PENDAFTARAN WALI / ORANG TUA ---
        if request.endpoint == 'main.register':
            parent_name = request.form.get('parent_name')
            contact = request.form.get('contact')
            password = request.form.get('password')
            address = request.form.get('address')
            child_name = request.form.get('child_name')
            child_birth = request.form.get('child_birth')
            gender = request.form.get('gender')

            if db.users.find_one({"email": contact}):
                flash("Email sudah terdaftar!", "warning")
                return redirect(url_for('main.register'))

            hashed_pw = generate_password_hash(password)
            user_result = db.users.insert_one({
                "username": parent_name, 
                "email": contact, 
                "password": hashed_pw,
                "address": address, 
                "role": "parent", 
                "created_at": datetime.utcnow()
            })
            
            birth_date = datetime.strptime(child_birth, '%Y-%m-%d') if child_birth else None
            db.children.insert_one({
                "parent_id": user_result.inserted_id, 
                "name": child_name,
                "birth_date": birth_date, 
                "gender": gender, 
                "created_at": datetime.utcnow()
            })
            flash("Registrasi Berhasil! Silakan Login.", "success")
            return redirect(url_for('main.login'))


        # --- PENDAFTARAN MITRA PSIKOLOG ---
        elif request.endpoint == 'main.register_psychologist':
            email = request.form.get('email')
            
            if db.users.find_one({"email": email}):
                flash("Email sudah terdaftar di sistem!", "warning")
                return redirect(url_for('main.register_psychologist'))

            # Proses Upload File STR
            str_filename = None
            if 'str_file' in request.files:
                file = request.files['str_file']
                if file.filename != '':
                    filename = secure_filename(f"STR_{email.split('@')[0]}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    str_filename = filename

            # Proses Upload File SIPPK
            sippk_filename = None
            if 'sippk_file' in request.files:
                file = request.files['sippk_file']
                if file.filename != '':
                    filename = secure_filename(f"SIPPK_{email.split('@')[0]}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    sippk_filename = filename

            username = request.form.get('username')
            whatsapp = request.form.get('whatsapp') 
            
            user_data = {
                "username": username,
                "email": email,
                "password": generate_password_hash(request.form.get('password')),
                "whatsapp": whatsapp if whatsapp else "-", # Jika kosong, isi dengan "-"
                "specialty": request.form.get('specialty'),
                "address": request.form.get('address'),
                "str_file": str_filename,
                "sippk_file": sippk_filename,
                "role": "psychologist",
                "is_verified": False,
                "created_at": datetime.utcnow()
            }
            db.users.insert_one(user_data)
            
            # --- KIRIM EMAIL NOTIFIKASI KE ADMIN ---
            try:
                admin_email = os.environ.get('ADMIN_EMAIL')
                if admin_email:
                    msg = Message(
                        subject="Pendaftaran Psikolog Baru Menunggu Verifikasi",
                        recipients=[admin_email],
                        html=f"""
                            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 10px;">
                                <h2 style="color: #0f766e;">Notifikasi KidsCare</h2>
                                <p>Halo Admin,</p>
                                <p>Terdapat pendaftaran Mitra Psikolog baru yang menunggu proses verifikasi Anda.</p>
                                
                                <div style="background-color: #f8fafc; padding: 15px; border-radius: 8px; margin: 20px 0;">
                                    <ul style="list-style-type: none; padding: 0; margin: 0; line-height: 1.8;">
                                        <li><b>Nama:</b> {username}</li>
                                        <li><b>Email:</b> {email}</li>
                                        <li><b>Spesialisasi:</b> {user_data['specialty']}</li>
                                    </ul>
                                </div>
                                
                                <p>Silakan login ke Panel Administrator untuk memeriksa dokumen STR/SIPPK dan menyetujui pendaftaran ini.</p>
                            </div>
                        """
                    )
                    mail.send(msg)
            except Exception as e:
                print(f"Gagal mengirim notif ke Admin: {e}")

            flash("Pendaftaran Mitra Psikolog berhasil! Menunggu verifikasi Admin.", "success")
            return redirect(url_for('main.login'))

    # Untuk metode GET (Menampilkan halaman form)
    return render_template('authentications/register/register.html')

@main_bp.route('/add-child', methods=['GET', 'POST'])
def add_child_profile():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
        
    if request.method == 'POST':
        child_name = request.form.get('child_name')
        birth_date_str = request.form.get('child_birth')
        gender = request.form.get('gender')
        
        # 1. Simpan data anak ke database
        db.children.insert_one({
            "parent_id": ObjectId(session['user_id']),
            "name": child_name,
            "birth_date": datetime.strptime(birth_date_str, '%Y-%m-%d'),
            "gender": gender,
            "created_at": datetime.utcnow()
        })
        
        # ==========================================
        # 2. BLOK PENGIRIMAN EMAIL NOTIFIKASI
        # ==========================================
        try:
            # Ambil data user (Wali) dari database berdasarkan session user_id
            user = db.users.find_one({"_id": ObjectId(session['user_id'])})
            
            if user and user.get('email'):
                parent_email = user.get('email')
                # Ambil nama parent, jika kosong set default 'Orang Tua'
                parent_name = user.get('username', 'Orang Tua') 
                
                msg = Message(
                    subject='Profil Anak Berhasil Ditambahkan - KidsCare',
                    recipients=[parent_email]
                )
                
                # Link menuju dashboard / mulai skrining
                dashboard_link = url_for('user.index', _external=True)
                
                msg.html = f"""
                <!DOCTYPE html>
                <html>
                <body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                    <div style="width: 100%; max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 24px; overflow: hidden; margin-top: 40px; margin-bottom: 40px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                        <div style="background: linear-gradient(135deg, #14b8a6, #0f766e); padding: 30px 20px; text-align: center;">
                            <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 900; letter-spacing: 1px;">KidsCare</h1>
                        </div>
                        <div style="padding: 40px 30px;">
                            <h2 style="color: #1e293b; font-size: 22px; margin-top: 0;">Halo, {parent_name}!</h2>
                            <p style="color: #64748b; font-size: 16px; line-height: 1.6;">
                                Pendaftaran akun melalui Google telah berhasil, dan profil si kecil <strong>{child_name}</strong> sudah tersimpan di sistem KidsCare Anda.
                            </p>
                            <p style="color: #64748b; font-size: 16px; line-height: 1.6;">
                                Sekarang Anda dapat memulai evaluasi perkembangan dan skrining secara mandiri.
                            </p>
                            <div style="text-align: center; margin: 30px 0;">
                                <a href="{dashboard_link}" style="display: inline-block; background-color: #14b8a6; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 12px; font-weight: bold; font-size: 14px;">Mulai Tes Skrining</a>
                            </div>
                        </div>
                    </div>
                </body>
                </html>
                """
                mail.send(msg)
        except Exception as e:
            # Print error ke terminal untuk debugging
            print(f"Gagal mengirim email notifikasi penambahan anak: {e}")
        # ==========================================

        session.pop('pending_child', None)
        return redirect(url_for('user.index'))
        
    return render_template('authentications/register/add_child.html')

@main_bp.route('/request_otp', methods=['POST'])
def request_otp():
    data = request.get_json()
    email = data.get('email')
    
    # 1. Cari user di database
    user = db.users.find_one({"email": email})
    
    if not user:
        return jsonify({
            "status": "error", 
            "message": "Email tidak terdaftar di sistem kami."
        }), 404
        
    # Ambil nama user untuk sapaan (gunakan 'Pengguna' jika kosong)
    nama_user = user.get('name', 'Pengguna')
        
    # 2. Buat 6 digit OTP acak
    otp_code = str(randint(100000, 999999))
    
    # 3. Atur waktu kedaluwarsa (misal: 10 menit dari sekarang)
    expiration_time = datetime.now() + timedelta(minutes=10)
    
    # 4. Simpan OTP dan waktu kedaluwarsa ke dokumen user tersebut
    db.users.update_one(
        {"email": email},
        {"$set": {
            "reset_otp": otp_code,
            "otp_expiration": expiration_time
        }}
    )
    
    # 5. Kirim Email ke User (Dengan Desain HTML)
    try:
        msg = Message(
            subject='Kode Reset Kata Sandi - KidsCare',
            recipients=[email]
        )
        
        # Fallback untuk aplikasi email lama yang tidak mendukung HTML
        msg.body = f"Halo {nama_user}, kode OTP Anda adalah {otp_code}. Berlaku 10 menit."
        
        # Desain HTML Email yang Menarik
        msg.html = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
            <div style="width: 100%; max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 24px; overflow: hidden; margin-top: 40px; margin-bottom: 40px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                
                <div style="background: linear-gradient(135deg, #14b8a6, #0f766e); padding: 30px 20px; text-align: center;">
                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 900; letter-spacing: 1px;">KidsCare</h1>
                    <p style="color: #ccfbf1; margin: 5px 0 0 0; font-size: 14px;">Layanan Tumbuh Kembang Anak</p>
                </div>
                
                <div style="padding: 40px 30px;">
                    <h2 style="color: #1e293b; font-size: 22px; margin-top: 0;">Halo, {user['username']}!</h2>
                    <p style="color: #64748b; font-size: 16px; line-height: 1.6;">
                        Kami menerima permintaan untuk mengatur ulang kata sandi akun KidsCare Anda. Silakan gunakan kode OTP di bawah ini untuk melanjutkan proses:
                    </p>
                    
                    <div style="text-align: center; margin: 40px 0;">
                        <div style="display: inline-block; background-color: #eef2ff; border: 2px dashed #818cf8; padding: 20px 40px; border-radius: 16px;">
                            <span style="font-size: 36px; font-weight: 900; color: #4f46e5; letter-spacing: 8px;">{otp_code}</span>
                        </div>
                    </div>
                    
                    <p style="color: #ef4444; font-size: 14px; text-align: center; font-weight: bold; background-color: #fef2f2; padding: 12px; border-radius: 8px;">
                        ⏳ Kode ini hanya berlaku selama 10 menit.
                    </p>
                    
                    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                    
                    <p style="color: #94a3b8; font-size: 13px; text-align: center; line-height: 1.5;">
                        Jika Anda tidak pernah meminta pengaturan ulang kata sandi, abaikan email ini dan pastikan akun Anda tetap aman. <strong>Jangan pernah membagikan kode OTP kepada siapa pun.</strong>
                    </p>
                </div>
                
                <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">&copy; {datetime.now().year} KidsCare Indonesia. Hak Cipta Dilindungi.</p>
                </div>
                
            </div>
        </body>
        </html>
        """
        
        mail.send(msg)
        return jsonify({"status": "success", "message": "OTP berhasil dikirim ke email."}), 200
        
    except Exception as e:
        print(f"Error sending email: {e}")
        return jsonify({"status": "error", "message": "Gagal mengirim email. Silakan coba lagi."}), 500


# ==========================================
# ROUTE 2: VERIFIKASI OTP & SIMPAN SANDI BARU
# ==========================================
@main_bp.route('/reset_password', methods=['POST'])
def reset_password():
    # Ambil data dari form submit Modal 2
    email = request.form.get('email')
    input_otp = request.form.get('otp')
    new_password = request.form.get('new_password')
    
    # 1. Cari user berdasarkan email
    user = db.users.find_one({"email": email})
    
    if not user:
        flash('Terjadi kesalahan. Data pengguna tidak ditemukan.', 'error')
        return redirect(url_for('main.login')) # Sesuaikan dengan route login Anda
        
    # 2. Cek apakah OTP cocok dan belum kedaluwarsa
    stored_otp = user.get('reset_otp')
    expiration = user.get('otp_expiration')
    
    # Validasi kesesuaian OTP
    if stored_otp != input_otp:
        flash('Kode OTP salah! Silakan coba lagi.', 'error')
        return redirect(url_for('main.login'))
        
    # Validasi waktu kedaluwarsa
    if expiration and datetime.now() > expiration:
        flash('Kode OTP sudah kedaluwarsa. Silakan minta kode baru.', 'error')
        return redirect(url_for('main.login'))
        
    # 3. Jika Valid, Hash password baru
    hashed_password = generate_password_hash(new_password)
    
    # 4. Update password di database & hapus OTP agar tidak bisa dipakai lagi
    db.users.update_one(
        {"email": email},
        {
            "$set": {"password": hashed_password},
            "$unset": {"reset_otp": "", "otp_expiration": ""}
        }
    )
    
    # 5. Selesai!
    flash('Kata sandi berhasil diubah! Silakan login dengan kata sandi baru.', 'success')
    return redirect(url_for('main.login'))

@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login'))


# ==========================================
# --- ADMIN ROUTES ---
# ==========================================
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Halaman Utama Dashboard Administrator"""
    
    # 1. Menghitung Statistik Utama
    total_parents = db.users.count_documents({"role": "parent"})
    total_psychs = db.users.count_documents({"role": "psychologist", "is_verified": True})
    pending_psychs = db.users.count_documents({"role": "psychologist", "is_verified": False})
    total_screenings = db.screening_tests.count_documents({})
    
    stats = {
        "parents": total_parents,
        "psychs": total_psychs,
        "pending_psychs": pending_psychs,
        "screenings": total_screenings
    }
    
    # 2. Mengambil 5 Orang Tua yang baru saja mendaftar
    recent_parents = list(db.users.find({"role": "parent"}).sort("created_at", -1).limit(5))
    
    # Menghitung jumlah anak & total tes yang pernah dilakukan oleh parent tersebut
    for parent in recent_parents:
        # Hitung anak
        children = list(db.children.find({"parent_id": parent['_id']}))
        parent['child_count'] = len(children)
        
        # Hitung tes skrining
        child_ids = [c['_id'] for c in children]
        if child_ids:
            parent['screening_count'] = db.screening_tests.count_documents({"child_id": {"$in": child_ids}})
        else:
            parent['screening_count'] = 0

    return render_template('admin/dashboard.html', stats=stats, recent_parents=recent_parents)

# --- MANAJEMEN PSIKOLOG ---
@admin_bp.route('/manage-psychologists')
@admin_required
def manage_psychologists():
    """Halaman Kelola & Verifikasi Psikolog"""
    # Mengambil psikolog yang belum diverifikasi
    pending = list(db.users.find({"role": "psychologist", "is_verified": False}).sort("created_at", -1))
    
    # Mengambil psikolog yang sudah aktif
    active = list(db.users.find({"role": "psychologist", "is_verified": True}).sort("created_at", -1))
    
    return render_template('admin/manage_psychologists.html', pending=pending, active=active)

@app.route('/admin/verify-psychologist/<user_id>/<action>')
def verify_psychologist(user_id, action):
    # Cari data psikolog di database
    user = db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user or user.get('role') != 'psychologist':
        flash("Data psikolog tidak ditemukan.", "danger")
        return redirect(url_for('admin.manage_users')) # Sesuaikan nama fungsi redirect Anda

    # JIKA ADMIN KLIK "SETUJUI"
    if action == 'approve':
        # 1. Update status di database menjadi True dan status active
        db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_verified": True, "status": "active"}}
        )
        
        # 2. KIRIM EMAIL NOTIFIKASI
        try:
            msg = Message(
                subject="Selamat! Akun Mitra Psikolog Anda Telah Disetujui",
                recipients=[user['email']],
                html=f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 10px;">
                        <h2 style="color: #0f766e;">Selamat datang di KidsCare!</h2>
                        <p>Halo <b>{user['username']}</b>,</p>
                        <p>Kabar baik! Pendaftaran Anda sebagai Mitra Psikolog di platform KidsCare telah berhasil <b>diverifikasi</b> oleh Administrator kami.</p>
                        <p>Sekarang Anda sudah dapat mengakses <i>Dashboard Professional</i> untuk mengatur jadwal praktik, membuat agenda, dan merespons konsultasi dari para orang tua.</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{url_for('main.login', _external=True)}" style="background-color: #14b8a6; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: bold;">Masuk ke Dashboard</a>
                        </div>
                        
                        <p>Terima kasih atas dedikasi Anda membantu tumbuh kembang anak-anak.</p>
                        <p style="color: #64748b; font-size: 12px; margin-top: 30px;">Salam hangat,<br>Tim KidsCare</p>
                    </div>
                """
            )
            mail.send(msg)
            flash(f"Akun {user['username']} disetujui dan email berhasil dikirim!", "success")
        
        except Exception as e:
            print(f"Error mengirim email: {e}")
            flash(f"Akun {user['username']} disetujui, namun sistem gagal mengirim email notifikasi.", "warning")

    # JIKA ADMIN KLIK "TOLAK"
    elif action == 'reject':
        # Menerapkan Soft Delete: Mengubah status, BUKAN menghapus permanen
        db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_verified": False, "status": "rejected"}}
        )
        flash(f"Pendaftaran {user['username']} telah ditolak dan diarsipkan.", "warning")
        
    # JIKA ADMIN KLIK "SUSPEND"
    elif action == 'suspend':
        # Menerapkan Suspend: Mengubah status untuk membekukan akun
        db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_verified": False, "status": "suspended"}}
        )
        flash(f"Akun {user['username']} telah ditangguhkan sementara.", "warning")

    return redirect(url_for('admin.manage_psychologists')) # Sesuaikan nama fungsi redirect Anda

# --- MANAJEMEN PENGGUNA ---
@admin_bp.route('/manage-users')
@admin_required
def manage_users():
    """Halaman Kelola Pengguna (Khusus Orang Tua)"""
    # HANYA panggil user yang role-nya "parent"
    users = list(db.users.find({"role": "parent"}).sort("created_at", -1))
    
    for u in users:
        # Panggil fungsi format_date_id untuk mengubah tanggal ke format Indonesia
        if isinstance(u.get('created_at'), datetime):
            date_str = u['created_at'].strftime('%Y-%m-%d')
            u['formatted_date'] = format_date_id(date_str)
        else:
            u['formatted_date'] = "Tanpa Data"
            
    return render_template('admin/manage_users.html', users=users)

@admin_bp.route('/user-action/<user_id>/<action>')
@admin_required
def user_action(user_id, action):
    """Menangani Soft Delete (Suspend) dan Aktivasi User Orang Tua"""
    user = db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        flash("Pengguna tidak ditemukan.", "danger")
        return redirect(url_for('admin.manage_users'))
        
    if action == 'suspend':
        # Soft delete: Ubah status menjadi suspended
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"status": "suspended"}})
        flash(f"Akun {user['username']} berhasil ditangguhkan.", "warning")
        
    elif action == 'activate':
        # Aktifkan kembali
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"status": "active"}})
        flash(f"Akun {user['username']} berhasil diaktifkan kembali.", "success")
        
    return redirect(url_for('admin.manage_users'))

# --- MANAJEMEN PERTANYAAN SKRINING ---
@admin_bp.route('/manage-questions')
@admin_required
def manage_questions():
    # Mengambil semua pertanyaan, urutkan berdasarkan urutan (order)
    questions = list(db.questions.find().sort("order", 1))
    return render_template('admin/manage_questions.html', questions=questions)

@admin_bp.route('/edit-question/<question_id>', methods=['POST'])
@admin_required
def edit_question(question_id):
    new_text = request.form.get('question_text')
    is_active = 'is_active' in request.form
    
    db.questions.update_one(
        {"_id": ObjectId(question_id)},
        {"$set": {"text": new_text, "is_active": is_active}}
    )
    return redirect(url_for('admin.manage_questions'))

# --- MANAJEMEN AGENDA ---
@admin_bp.route('/manage-agenda')
@admin_required
def manage_agenda():
    # Mengambil semua agenda dari koleksi 'agendas'
    agendas = list(db.events.find().sort("date", 1))
    return render_template('admin/manage_agenda.html', agendas=agendas)

@admin_bp.route('/delete-agenda/<agenda_id>')
@admin_required
def delete_agenda(agenda_id):
    db.events.delete_one({"_id": ObjectId(agenda_id)})
    return redirect(url_for('admin.manage_agenda'))

@admin_bp.route('/reports')
@admin_required
def reports():
    """Halaman Laporan Statistik Skrining"""
    
    # 1. Pastikan database Anda memiliki koneksi (db)
    # Pastikan pipeline agregasi di sini
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ]
    
    # Bungkus dengan list() agar menjadi data statis (bukan cursor)
    distribution = list(db.screening_tests.aggregate(pipeline))
    
    # 2. Ambil 20 data skrining terakhir
    recent_tests = list(db.screening_tests.find().sort("created_at", -1).limit(20))
    
    # 3. Proses data untuk tampilan
    for t in recent_tests:
        # Ambil nama anak
        child = db.children.find_one({"_id": t.get('child_id')})
        t['child_name'] = child['name'] if child else "N/A"
        
        # Proses Tanggal menggunakan fungsi Anda
        if isinstance(t.get('created_at'), datetime):
            # Mengubah datetime jadi string YYYY-MM-DD
            date_str = t['created_at'].strftime('%Y-%m-%d')
            # Memanggil fungsi format_date_id milik Anda
            t['formatted_date'] = format_date_id(date_str)
        else:
            t['formatted_date'] = "Tanggal Tidak Valid"
            
    # Pastikan semua variabel yang dikirim ke HTML sudah terdefinisi di atas
    return render_template(
        'admin/reports.html', 
        distribution=distribution, 
        recent_tests=recent_tests
    )
# ------------------------------------
# ==========================================
# USER ROUTES
# ==========================================

@user_bp.route('/')
def index():
    if 'user_id' not in session: 
        return redirect(url_for('main.login'))
    user_data = db.users.find_one({"_id": ObjectId(session['user_id'])})
    children = list(db.children.find({"parent_id": ObjectId(session['user_id'])}).sort("created_at", 1))
    default_child = children[0] if children else None

    if default_child:
        latest_test = db.screening_tests.find_one(
            {"child_id": default_child['_id']}, 
            sort=[("created_at", -1)]
        )
        default_child['status'] = latest_test['category'] if latest_test else "Belum Pernah Tes"

    events = list(db.events.find().sort("created_at", -1).limit(3))
 
    for event in events:
        event['_id'] = str(event['_id'])
    return render_template('users/index.html', 
                           user=user_data, 
                           child=default_child, 
                           children=children, 
                           upcoming_events=events)

# --- PROFIL USER ---
@user_bp.route('/profil')
def profil_user():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    user = db.users.find_one({"_id": ObjectId(session['user_id'])})
    children = list(db.children.find({"parent_id": ObjectId(session['user_id'])}).sort("created_at", 1))
    for child in children:
        latest_test = db.screening_tests.find_one({"child_id": child['_id']}, sort=[("created_at", -1)])
        child['status'] = latest_test['category'] if latest_test else "Belum Pernah Tes"
    return render_template('users/profil/profil_user.html', user=user, children=children)

@user_bp.route('/profil/update_account', methods=['POST'])
def update_account():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    update_data = {"username": name, "email": email}
    if password and password != "********":
        update_data["password"] = generate_password_hash(password)
    db.users.update_one({"_id": ObjectId(session['user_id'])}, {"$set": update_data})
    flash("Informasi akun berhasil diperbarui!", "success")
    return redirect(url_for('user.profil_user'))

@user_bp.route('/profil/add_child', methods=['POST'])
def add_child():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    name = request.form.get('child_name')
    birth_date = request.form.get('child_birth')
    gender = request.form.get('gender')
    db.children.insert_one({
        "parent_id": ObjectId(session['user_id']),
        "name": name,
        "birth_date": datetime.strptime(birth_date, '%Y-%m-%d'),
        "gender": gender,
        "created_at": datetime.utcnow()
    })
    flash("Data anak berhasil ditambahkan!", "success")
    return redirect(url_for('user.profil_user'))

@user_bp.route('/profil/edit_child', methods=['POST'])
def edit_child():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    
    child_id = request.form.get('child_id')
    name = request.form.get('child_name')
    birth_date = request.form.get('child_birth')
    gender = request.form.get('gender')
    
    try:
        # Update data berdasarkan ID anak dan ID parent (keamanan)
        db.children.update_one(
            {"_id": ObjectId(child_id), "parent_id": ObjectId(session['user_id'])},
            {"$set": {
                "name": name,
                "birth_date": datetime.strptime(birth_date, '%Y-%m-%d'),
                "gender": gender
            }}
        )
        flash(f"Profil {name} berhasil diperbarui!", "success")
    except Exception as e:
        flash("Terjadi kesalahan saat memperbarui data anak.", "danger")
        
    return redirect(url_for('user.profil_user'))

@user_bp.route('/profil/delete_child/<id>')
def delete_child(id):
    if 'user_id' not in session: return redirect(url_for('main.login'))
    db.children.delete_one({"_id": ObjectId(id), "parent_id": ObjectId(session['user_id'])})
    flash("Data anak telah dihapus.", "info")
    return redirect(url_for('user.profil_user'))

@user_bp.route('/profil/set_default/<id>')
def set_default_child(id):
    if 'user_id' not in session: return redirect(url_for('main.login'))

    target_child = db.children.find_one({"_id": ObjectId(id)})
    if not target_child:
        flash("Data anak tidak ditemukan.", "danger")
        return redirect(url_for('user.profil_user'))

    db.children.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"created_at": datetime(2000, 1, 1)}} # Set ke tahun 2000 agar jadi yang paling lama
    )
    
    db.children.update_many(
        {"_id": {"$ne": ObjectId(id)}, "parent_id": ObjectId(session['user_id'])},
        {"$set": {"created_at": datetime.utcnow()}}
    )

    flash(f"{target_child['name']} kini menjadi Profil Utama untuk skrining.", "success")
    return redirect(url_for('user.profil_user'))

@user_bp.route('/riwayat-rekomendasi')
def riwayat_rekomendasi():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    
    parent_id = ObjectId(session['user_id'])
    summaries = list(db.consultation_summaries.find({"parent_id": parent_id}).sort("created_at", -1))
    
    for s in summaries:
        psych = db.users.find_one({"_id": s['psychologist_id']})
        child = db.children.find_one({"_id": s['child_id']})
        s['psych_name'] = psych['username'] if psych else "Ahli KidsCare"
        s['child_name'] = child['name'] if child else "Anak"
        
        # Cek apakah ada chat untuk memudahkan navigasi balik
        con = db.consultations.find_one({"parent_id": parent_id, "psychologist_id": s['psychologist_id']})
        s['consult_id'] = str(con['_id']) if con else None

    return render_template('users/rekomendasi/riwayat_rekomendasi.html', summaries=summaries)

# --- FITUR SKRINING, EDUKASI & KONSULTASI ---
@user_bp.route('/skrining')
def test_skrining():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    # Menampilkan daftar anak agar orang tua bisa memilih siapa yang akan dites
    children = list(db.children.find({"parent_id": ObjectId(session['user_id'])}).sort("created_at", 1))
    return render_template('users/testskrining/test_skrining.html', children=children)

@user_bp.route('/skrining/form')
def skrining_form():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    
    # Ambil ID anak dari parameter URL
    child_id = request.args.get('child_id')
    if not child_id:
        flash("Silakan pilih anak terlebih dahulu!", "warning")
        return redirect(url_for('user.test_skrining'))
        
    child = db.children.find_one({"_id": ObjectId(child_id)})
    questions = list(db.questions.find().sort("order", 1))
    
    return render_template('users/testskrining/skrining_form.html', questions=questions, child=child)

@user_bp.route('/predict', methods=['POST'])
def predict():
    if 'user_id' not in session: 
        return redirect(url_for('main.login'))
        
    try:
        # 1. Ambil ID Anak dari form yang disembunyikan (hidden input)
        child_id_str = request.form.get('child_id')
        if not child_id_str:
            return "ID Anak tidak ditemukan."

        # 2. Ambil seluruh pertanyaan dari database dan urutkan
        # Pastikan "q_id" adalah nama field nomor urut di collection questions Anda
        questions = list(db.questions.find().sort("q_id", 1)) 
        
        in_score = 0
        hy_score = 0
        additional_met = True
        answers_data = [] 
        
        # 3. KUNCI UTAMA: start=1 agar Python mencari request q1, q2, dst.
        for i, q in enumerate(questions, start=1):
            
            val = request.form.get(f'q{i}')
            
            # Lewati jika kebetulan tidak ada jawaban yang tertangkap
            if val is None: 
                continue 
                
            score = int(val)
            
            # Terjemahkan angka skor form menjadi teks untuk disimpan di laporan/riwayat
            if q.get('type') == 'likert':
                labels = {0: 'Tidak Pernah', 1: 'Jarang', 2: 'Sering', 3: 'Sangat Sering'}
            else:
                labels = {1: 'Ya', 0: 'Tidak'}
            
            ans_label = labels.get(score, str(score))
            
            # Tambahkan riwayat jawaban per soal
            answers_data.append({
                "question": q['text'],
                "answer": ans_label
            })

            # 4. PENILAIAN SKOR (Gunakan .lower() agar aman dari perbedaan huruf kapital)
            kat = q.get('category', '').lower()
            
            if kat == 'inattention' and score >= 2: 
                in_score += 1
            elif kat == 'hyperactivity' and score >= 2: 
                hy_score += 1
            elif kat == 'additional' and score == 0: 
                # Jika ada satu saja kriteria tambahan yang bernilai 0 (Tidak), syarat gagal
                additional_met = False

        # 5. PENENTUAN DIAGNOSIS DSM-5
        category = "Normal / Risiko Rendah"
        
        # Diagnosis ADHD HANYA diberikan jika kriteria tambahan (usia & lingkungan) bernilai 'Ya' semua
        if additional_met: 
            if in_score >= 6 and hy_score >= 6: 
                category = "ADHD Tipe Campuran"
            elif in_score >= 6: 
                category = "ADHD Tipe Inatensi"
            elif hy_score >= 6: 
                category = "ADHD Tipe Hiperaktif-Impulsivitas"

        # 6. SIMPAN KE DATABASE
        db.screening_tests.insert_one({
            "child_id": ObjectId(child_id_str),
            "inattentive_score": in_score,
            "hyperactive_score": hy_score,
            "category": category,
            "answers": answers_data,
            "created_at": datetime.utcnow()
        })
        
        # 7. TAMPILKAN KE HALAMAN HASIL
        return render_template('users/testskrining/result.html', result=category, in_score=in_score, hy_score=hy_score)
        
    except Exception as e:
        return f"Terjadi kesalahan sistem: {str(e)}"

@user_bp.route('/skrining/riwayat')
@user_bp.route('/skrining/riwayat/<child_id>')
def riwayat_skrining(child_id=None):
    if 'user_id' not in session: 
        return redirect(url_for('main.login'))
    
    parent_id = ObjectId(session['user_id'])
    children = list(db.children.find({"parent_id": parent_id}).sort("created_at", 1))
    
    page = int(request.args.get('page', 1))
    per_page = 5
    offset = (page - 1) * per_page
    
    selected_child_id = child_id or request.args.get('child_id')
    
    if not selected_child_id and children:
        selected_child_id = str(children[0]['_id'])
    
    history = []
    selected_child = None
    total_records = 0
    
    if selected_child_id:
        try:
            selected_child = db.children.find_one({"_id": ObjectId(selected_child_id)})
            if selected_child:
                query = {
                    "$or": [
                        {"child_id": ObjectId(selected_child_id)},
                        {"child_id": str(selected_child_id)}
                    ]
                }
                total_records = db.screening_tests.count_documents(query)
                history = list(db.screening_tests.find(query)
                               .sort("created_at", -1)
                               .skip(offset)
                               .limit(per_page))
        except:
            return redirect(url_for('user.riwayat_skrining'))
            
    has_next = (offset + per_page) < total_records
    has_prev = page > 1
    
    return render_template('users/riwayatskrining/riwayat_skrining.html', 
                           history=history, 
                           children=children, 
                           selected_child=selected_child,
                           page=page,
                           has_next=has_next,
                           has_prev=has_prev)

# --- EDUKASI & KONSULTASI ---
@user_bp.route('/edukasi')
def edukasi_user():
    if 'user_id' not in session: 
        return redirect(url_for('main.login'))
    
    active_filter = request.args.get('filter', 'all')
    
    YOUTUBE_API_KEY = "AIzaSyByDUY6r68xZhp2YsMUUI69yq4Z2-MrUrY"
    
    videos = []
    events = []

    if active_filter in ['all', 'jadwal-agenda']:
        events = list(db.events.find().sort("created_at", -1))
        for e in events:
            e['_id'] = str(e['_id'])

    if active_filter != 'jadwal-agenda':
        yt_cat = 'pengertian-adhd' if active_filter == 'all' else active_filter
        try:
            videos = get_realtime_adhd_videos(YOUTUBE_API_KEY, yt_cat)
        except Exception as e:
            print(f"YouTube Error: {e}")
            videos = []
        
    return render_template('users/edukasi/edukasi_user.html', 
                           videos=videos, 
                           events=events, 
                           active_filter=active_filter)

@user_bp.route('/edukasi/detail/<id>')
def edukasi_detail(id):
    """Endpoint: user.edukasi_detail"""
    video_data = {
        'video_url': f"https://www.youtube.com/watch?v={id}",
        'title': request.args.get('title', 'Video Edukasi'),
        'description': request.args.get('desc', 'Tidak ada deskripsi.'),
        'category': request.args.get('cat', 'Edukasi')
    }
    return render_template('users/edukasi/edukasi_detail.html', video=video_data)

@user_bp.route('/konsultasi')
@user_bp.route('/konsultasi/<psych_id>')
def konsultasi_psikolog(psych_id=None):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    parent_id = ObjectId(session['user_id'])

    psychologists = list(db.users.find({"role": "psychologist", "is_verified": True}))
    all_children = list(db.children.find({"parent_id": parent_id}))
    
    selected_psych = None
    if psych_id:
        try:
            selected_psych = db.users.find_one({"_id": ObjectId(psych_id)})
        except: pass
    if not selected_psych and psychologists:
        selected_psych = psychologists[0]

    active_cons = list(db.consultations.find({"parent_id": parent_id, "status": "active"}))
    
    busy_child_ids = set() # Anak yang sudah punya psikolog (siapa pun itu)
    this_psych_sessions = [] # Sesi yang spesifik dengan psikolog yang sedang dilihat
    
    for con in active_cons:
        child_id_str = str(con['child_id'])
        busy_child_ids.add(child_id_str)
        
        # Jika sesi ini adalah dengan psikolog yang sedang dilihat
        if str(con['psychologist_id']) == str(selected_psych['_id']):
            child_data = db.children.find_one({"_id": con['child_id']})
            this_psych_sessions.append({
                "consult_id": str(con['_id']),
                "child_name": child_data['name'] if child_data else "Anak"
            })

    # Anak yang tersedia untuk dikonsultasikan (belum punya sesi aktif di mana pun)
    available_children = [c for c in all_children if str(c['_id']) not in busy_child_ids]

    schedules = []
    if selected_psych:
        day_order = {"Senin": 0, "Selasa": 1, "Rabu": 2, "Kamis": 3, "Jumat": 4, "Sabtu": 5, "Minggu": 6}
        schedules = list(db.schedules.find({"psychologist_id": selected_psych['_id'], "$or": [{"is_holiday": False}, {"is_holiday": {"$exists": False}}]}))
        schedules.sort(key=lambda x: day_order.get(x['day'], 7))

    return render_template('users/konsultasi/konsultasi_psikolog.html', 
                           psychologists=psychologists, 
                           selected_psych=selected_psych,
                           schedules=schedules,
                           this_psych_sessions=this_psych_sessions,
                           available_children=available_children,
                           total_children_count=len(all_children))

@user_bp.route('/konsultasi/switch', methods=['POST'])
def switch_psychologist():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    parent_id = ObjectId(session['user_id'])
    user_data = db.users.find_one({"_id": parent_id})
    
    if user_data.get('switch_count', 0) >= 1:
        flash("Batas ganti ahli sudah habis.", "danger")
        return redirect(url_for('user.konsultasi_psikolog'))
        
    db.consultations.update_many(
        {"parent_id": parent_id, "status": "active"},
        {"$set": {"status": "closed", "closed_at": datetime.now()}}
    )
    db.users.update_one({"_id": parent_id}, {"$inc": {"switch_count": 1}})
    flash("Anda sekarang bisa memilih psikolog baru.", "success")
    return redirect(url_for('user.konsultasi_psikolog'))

# ==========================================
# --- PSYCHOLOGIST ROUTES ---
# ==========================================
@psych_bp.route('/')
def dashboard():
    """Halaman Utama Dashboard Psikolog"""
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return redirect(url_for('main.login'))
    
    psych_id = ObjectId(session['user_id'])
    
    consultations = list(db.consultations.find({"psychologist_id": psych_id, "status": "active"}).sort("created_at", -1))
    for c in consultations:
        parent = db.users.find_one({"_id": c['parent_id']})
        c['parent_name'] = parent['username'] if parent else "Orang Tua"
  
    day_order = {"Senin": 0, "Selasa": 1, "Rabu": 2, "Kamis": 3, "Jumat": 4, "Sabtu": 5, "Minggu": 6}
    routine_schedules = list(db.schedules.find({
        "psychologist_id": psych_id,
        "$or": [
            {"is_holiday": False},
            {"is_holiday": {"$exists": False}}
        ]
    }))
    routine_schedules.sort(key=lambda x: day_order.get(x['day'], 7))

    my_events = list(db.events.find({"psychologist_id": psych_id}).sort("created_at", -1).limit(3))

    return render_template('psikolog/dashboard.html', 
                           consultations=consultations, 
                           schedules=routine_schedules,
                           upcoming_events=my_events)

@psych_bp.route('/schedule', methods=['GET', 'POST'])
def schedule_management():
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return redirect(url_for('main.login'))
    
    psych_id = ObjectId(session['user_id'])
    
    if request.method == 'POST':
        form_type = request.form.get('type') 
        
        if form_type == 'routine':
            selected_days = request.form.getlist('days')
            status = request.form.get('status')
            
            # Jika Libur, jam kita set default atau kosong
            if status == 'Libur':
                start_time = "00:00"
                end_time = "00:00"
            else:
                start_time = request.form.get('start_time')
                end_time = request.form.get('end_time')
            
            if not selected_days:
                flash("Pilih minimal satu hari untuk jadwal rutin!", "warning")
            else:
                for day_name in selected_days:
                    # Update atau Insert agar tidak duplikat di hari yang sama
                    db.schedules.update_one(
                        {"psychologist_id": psych_id, "day": day_name, "is_holiday": False},
                        {"$set": {
                            "start_time": start_time,
                            "end_time": end_time,
                            "status": status,
                            "is_holiday": False,
                            "created_at": datetime.now()
                        }},
                        upsert=True
                    )
                flash(f"Berhasil memperbarui jadwal rutin untuk {len(selected_days)} hari.", "success")

        elif form_type == 'holiday':
            specific_date = request.form.get('specific_date') 
            note = request.form.get('note')
     
            formatted_date = format_date_id(specific_date)
            day_name = get_indonesian_day(specific_date)
            
            db.schedules.insert_one({
                "psychologist_id": psych_id,
                "day": day_name,
                "is_holiday": True,
                "date_label": formatted_date, 
                "note": note,
                "start_time": "00:00",
                "end_time": "23:59",
                "status": "Libur",
                "created_at": datetime.now()
            })
            flash(f"Berhasil mengatur libur pada {formatted_date}.", "success")
            
        return redirect(url_for('psychologist.schedule_management'))

    schedules = list(db.schedules.find({"psychologist_id": psych_id}).sort("created_at", -1))
    return render_template('psikolog/jadwal_praktik.html', schedules=schedules)

@psych_bp.route('/schedule/edit/<id>', methods=['POST'])
def edit_schedule(id):
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return abort(403)
    
    db.schedules.update_one(
        {"_id": ObjectId(id), "psychologist_id": ObjectId(session['user_id'])},
        {"$set": {
            "start_time": request.form.get('start_time'),
            "end_time": request.form.get('end_time'),
            "status": request.form.get('status')
        }}
    )
    flash("Perubahan jadwal berhasil disimpan.", "success")
    return redirect(url_for('psychologist.schedule_management'))

@psych_bp.route('/schedule/delete/<id>')
def delete_schedule(id):
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return abort(403)
    
    db.schedules.delete_one({"_id": ObjectId(id), "psychologist_id": ObjectId(session['user_id'])})
    flash("Jadwal/Libur berhasil dihapus.", "info")
    return redirect(url_for('psychologist.schedule_management'))

@psych_bp.route('/events', methods=['GET', 'POST'])
def event_management():
    """Manajemen Agenda Webinar / Workshop oleh Psikolog"""
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return redirect(url_for('main.login'))
    
    psych_id = ObjectId(session['user_id'])
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        date = request.form.get('date') 
        time = request.form.get('time')
        event_type = request.form.get('type') 
        link = request.form.get('link')

        formatted_date = format_date_id(date)
        
        db.events.insert_one({
            "psychologist_id": psych_id,
            "psychologist_name": session.get('name'),
            "title": title,
            "description": description,
            "date": formatted_date,
            "raw_date": date,
            "time": time,
            "type": event_type,
            "registration_link": link,
            "created_at": datetime.now()
        })
        flash("Kegiatan baru berhasil dipublikasikan!", "success")
        return redirect(url_for('psychologist.event_management'))

    events = list(db.events.find({"psychologist_id": psych_id}).sort("created_at", -1))
    return render_template('psikolog/info_kegiatan.html', events=events)

@psych_bp.route('/events/edit/<id>', methods=['POST'])
def edit_event(id):
    """Rute untuk memperbarui data kegiatan yang sudah ada"""
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return abort(403)
    
    psych_id = ObjectId(session['user_id'])
    
    # Ambil data dari form modal edit di Canvas
    title = request.form.get('title')
    description = request.form.get('description')
    date = request.form.get('date') 
    time = request.form.get('time')
    event_type = request.form.get('type')
    link = request.form.get('link')
    formatted_date = format_date_id(date)
    
    # Update dokumen di koleksi 'events'
    db.events.update_one(
        {"_id": ObjectId(id), "psychologist_id": psych_id},
        {"$set": {
            "title": title,
            "description": description,
            "date": formatted_date,
            "raw_date": date,
            "time": time,
            "type": event_type,
            "registration_link": link
        }}
    )
    
    flash("Agenda berhasil diperbarui!", "success")
    return redirect(url_for('psychologist.event_management'))

@psych_bp.route('/events/delete/<id>')
def delete_event(id):
    """Menghapus Agenda Kegiatan"""
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return abort(403)
    
    db.events.delete_one({"_id": ObjectId(id), "psychologist_id": ObjectId(session['user_id'])})
    flash("Kegiatan telah dihapus dari publikasi.", "info")
    return redirect(url_for('psychologist.event_management'))

@psych_bp.route('/log-aktivitas')
def log_aktivitas():
    """
    Menampilkan antrean rekomendasi: Hanya menampilkan anak yang 
    memiliki bimbingan aktif dengan psikolog yang sedang login.
    """
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return redirect(url_for('main.login'))
    
    psych_id = ObjectId(session['user_id'])
    
    # Agregasi: Kelompokkan tes berdasarkan child_id dan urutkan
    pipeline = [
        {"$sort": {"created_at": -1}},
        {
            "$group": {
                "_id": "$child_id", 
                "latest_test_id": {"$first": "$_id"},
                "category": {"$first": "$category"},
                "inattentive_score": {"$first": "$inattentive_score"},
                "hyperactive_score": {"$first": "$hyperactive_score"},
                "created_at": {"$first": "$created_at"},
                "total_tests": {"$sum": 1},
                "all_history": {
                    "$push": {
                        "date": "$created_at",
                        "category": "$category",
                        "in_score": "$inattentive_score",
                        "hy_score": "$hyperactive_score"
                    }
                }
            }
        },
        {"$sort": {"created_at": -1}}
    ]
    
    grouped_results = list(db.screening_tests.aggregate(pipeline))
    
    patient_logs = []
    for entry in grouped_results:
        child = db.children.find_one({"_id": entry['_id']})
        if not child: continue
            
        parent = db.users.find_one({"_id": child['parent_id']})
        if not parent: continue

        consultation = db.consultations.find_one({
            "parent_id": parent['_id'],
            "psychologist_id": psych_id,
            "child_id": child['_id'],
            "status": "active"
        })
 
        if not consultation:
            continue
 
        formatted_history = []
        for h in entry['all_history']:
            h_copy = h.copy()
            if isinstance(h['date'], datetime):
                h_copy['date'] = h['date'].isoformat()
            formatted_history.append(h_copy)

        # Cek apakah sudah ada laporan/rekomendasi untuk tes terbaru ini
        summary = db.consultation_summaries.find_one({
            "test_id": entry['latest_test_id'],
            "psychologist_id": psych_id
        })
        
        patient_logs.append({
            "test_id": str(entry['latest_test_id']),
            "child_name": child['name'],
            "parent_name": parent['username'],
            "category": entry['category'],
            "scores": f"IN: {entry['inattentive_score']} | HY: {entry['hyperactive_score']}",
            "total_screenings": entry['total_tests'],
            "history_data": formatted_history,
            "has_chat": True,
            "consult_id": str(consultation['_id']),
            "has_summary": True if summary else False,
            "last_updated": entry['created_at'],
            "summary_data": summary
        })

    return render_template('psikolog/log_aktivitas.html', logs=patient_logs)

# --- EDUKASI & KONSULTASI ---
@psych_bp.route('/consultations')
@psych_bp.route('/consultations/<consult_id>')
def consultation_list(consult_id=None):
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return redirect(url_for('main.login'))
    
    psych_id = ObjectId(session['user_id'])
    consultations = list(db.consultations.find({"psychologist_id": psych_id}).sort("last_time", -1))
    
    for con in consultations:
        parent = db.users.find_one({"_id": con['parent_id']})
        con['parent_name'] = parent['username'] if parent else "Orang Tua"
        last_msg = db.messages.find_one({"consultation_id": con['_id']}, sort=[("timestamp", -1)])
        con['last_message'] = last_msg['content'] if last_msg else "Sesi dimulai."
        con['last_time'] = last_msg['timestamp'] if last_msg else con['created_at']

    selected_con = None
    messages = []
    
    if consult_id:
        try:
            selected_con = db.consultations.find_one({"_id": ObjectId(consult_id)})
            if selected_con:
                parent = db.users.find_one({"_id": selected_con['parent_id']})
                selected_con['parent_name'] = parent['username'] if parent else "User"
                c_id = selected_con.get('child_id')
                child = db.children.find_one({"_id": ObjectId(c_id)}) if c_id else db.children.find_one({"parent_id": selected_con['parent_id']})
                
                if child:
                    selected_con['child_name'] = child['name']
                    last_test = db.screening_tests.find_one({"child_id": child['_id']}, sort=[("created_at", -1)])
                    selected_con['child_status'] = last_test['category'] if last_test else "Belum Skrining"
                else:
                    selected_con['child_name'] = "N/A"
                    selected_con['child_status'] = "-"

                messages = list(db.messages.find({"consultation_id": ObjectId(consult_id)}).sort("timestamp", 1))
        except:
            return redirect(url_for('psychologist.consultation_list'))

    return render_template('psikolog/daftar_konsultasi.html', 
                           consultations=consultations, 
                           selected_con=selected_con, 
                           messages=messages)

@psych_bp.route('/consultation/save_summary', methods=['POST'])
def save_consultation_summary():
    """
    Menyimpan ulasan dan langkah tindak lanjut klinis untuk pasien aktif.
    """
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return abort(403)
    
    psych_id = ObjectId(session['user_id'])
    test_id = request.form.get('test_id')
    summary_text = request.form.get('summary_text')
    raw_recs = request.form.get('recommendations', '').split('\n')
    recommendations = [r.strip() for r in raw_recs if r.strip()]

    try:
        # 1. Cari data tes
        test_data = db.screening_tests.find_one({"_id": ObjectId(test_id)})
        if not test_data:
            flash("Data skrining tidak ditemukan.", "danger")
            return redirect(url_for('psychologist.log_aktivitas'))

        child = db.children.find_one({"_id": test_data['child_id']})
        if not child:
            flash("Data profil anak tidak ditemukan.", "danger")
            return redirect(url_for('psychologist.log_aktivitas'))
            
        # 2. VALIDASI KEAMANAN: Pastikan ini memang pasien aktif psikolog ini
        consultation = db.consultations.find_one({
            "psychologist_id": psych_id,
            "child_id": child['_id'],
            "status": "active"
        })
        
        if not consultation:
            flash("Akses ditolak! Anak ini bukan pasien aktif Anda.", "danger")
            return redirect(url_for('psychologist.log_aktivitas'))

        # 3. Lakukan Penyimpanan / Pembaruan Data
        summary_data = {
            "test_id": ObjectId(test_id),
            "psychologist_id": psych_id,
            "parent_id": child['parent_id'],
            "child_id": child['_id'],
            "summary_text": summary_text,
            "recommendations": recommendations,
            "created_at": datetime.now()
        }

        # Simpan berdasarkan test_id agar satu hasil tes memiliki satu laporan unik
        db.consultation_summaries.update_one(
            {
                "test_id": ObjectId(test_id),
                "psychologist_id": psych_id
            },
            {"$set": summary_data},
            upsert=True
        )
        
        flash(f"Rekomendasi klinis untuk {child['name']} berhasil diterbitkan.", "success")
    except Exception as e:
        flash(f"Gagal menyimpan data: {str(e)}", "danger")

    return redirect(url_for('psychologist.log_aktivitas'))

# --- PROFIL PSIKOLOG ---
@psych_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    """
    Mengelola profil profesional psikolog.
    Mendukung tampilan data (GET) dan pembaruan data (POST).
    """
    # 1. Proteksi Akses: Pastikan user login sebagai psikolog
    if 'user_id' not in session or session.get('role') != 'psychologist':
        return redirect(url_for('main.login'))
    
    psych_id = ObjectId(session['user_id'])
    
    # 2. Logika Update Data (POST)
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        whatsapp = request.form.get('whatsapp')
        specialization = request.form.get('specialization')
        address = request.form.get('address')
        password = request.form.get('password')
        
        # Siapkan paket data untuk diupdate
        update_fields = {
            "username": username,
            "email": email,
            "whatsapp": whatsapp,
            "specialization": specialization,
            "address": address
        }
        
        # Validasi Password: Hanya diubah jika input tidak kosong
        if password and len(password) >= 6:
            update_fields["password"] = generate_password_hash(password)
        elif password and len(password) < 6 and password:
            flash("Gagal: Kata sandi minimal harus 6 karakter.", "danger")
            return redirect(url_for('psychologist.profile'))
            
        try:
            # Eksekusi pembaruan ke koleksi 'users'
            db.users.update_one(
                {"_id": psych_id}, 
                {"$set": update_fields}
            )
            
            # Sinkronisasi Nama di Sesi (agar nama di sidebar/header langsung berubah)
            session['name'] = username
            
            flash("Profil profesional Anda berhasil diperbarui!", "success")
        except Exception as e:
            flash(f"Terjadi kesalahan sistem: {str(e)}", "danger")
            
        return redirect(url_for('psychologist.profile'))

    # 3. Logika Tampilan Data (GET)
    # Ambil data psikolog paling mutakhir dari database
    psych_data = db.users.find_one({"_id": psych_id})
    
    if not psych_data:
        flash("Data akun tidak ditemukan.", "danger")
        return redirect(url_for('main.logout'))
        
    return render_template('psikolog/profil.html', psych=psych_data)

# Update start_consultation untuk menangani multiple checkbox
@consult_bp.route('/start/<psych_id>', methods=['POST'])
def start_consultation(psych_id):
    if 'user_id' not in session: return redirect(url_for('main.login'))
    parent_id = ObjectId(session['user_id'])
    
    # Mengambil list ID anak dari checkbox
    child_ids = request.form.getlist('child_ids')
    
    if not child_ids:
        flash("Pilih minimal satu anak.", "warning")
        return redirect(url_for('user.konsultasi_psikolog', psych_id=psych_id))

    for cid in child_ids:
        # Buat sesi baru untuk setiap anak yang dipilih
        db.consultations.insert_one({
            "parent_id": parent_id,
            "psychologist_id": ObjectId(psych_id),
            "child_id": ObjectId(cid),
            "status": "active",
            "last_message": "Sesi baru dimulai",
            "last_time": datetime.now(),
            "created_at": datetime.now()
        })
    
    flash(f"Berhasil memulai sesi untuk {len(child_ids)} anak.", "success")
    return redirect(url_for('user.konsultasi_psikolog', psych_id=psych_id))

@consult_bp.route('/chat/<consult_id>', methods=['GET', 'POST'])
def room_chat(consult_id):
    """
    Ruang percakapan terenkripsi.
    """
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
    
    c_oid = ObjectId(consult_id)
    
    if request.method == 'POST':
        content = request.form.get('message')
        if content:
            db.messages.insert_one({
                "consultation_id": c_oid,
                "sender_id": ObjectId(session['user_id']),
                "content": content,
                "timestamp": datetime.now()
            })
            db.consultations.update_one(
                {"_id": c_oid},
                {"$set": {"last_message": content, "last_time": datetime.now()}}
            )
        
        # Jika psikolog yang balas, balikkan ke daftar konsultasi mereka
        if session.get('role') == 'psychologist':
            return redirect(url_for('psychologist.consultation_list', consult_id=consult_id))
        return redirect(url_for('consult.room_chat', consult_id=consult_id))

    consultation = db.consultations.find_one({"_id": c_oid})
    if not consultation:
        return redirect(url_for('user.konsultasi_psikolog'))
        
    is_parent = session.get('role') == 'parent'
    other_party_id = consultation['psychologist_id'] if is_parent else consultation['parent_id']
    other_party = db.users.find_one({"_id": other_party_id})
    messages = list(db.messages.find({"consultation_id": c_oid}).sort("timestamp", 1))
    
    return render_template('users/konsultasi/room_chat.html', 
                           consultation=consultation, 
                           messages=messages, 
                           other_party=other_party)


app.register_blueprint(main_bp);
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)
app.register_blueprint(consult_bp)
app.register_blueprint(psych_bp)

if __name__ == '__main__':
    app.run(debug=True, port=5000),