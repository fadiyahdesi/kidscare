from flask import Flask, render_template, request, redirect, session, url_for, Blueprint, flash, abort
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__,
            template_folder='app/templates',
            static_folder='app/static')
app.secret_key = 'kidscare-secret-key-dev'

# --- 1. KONEKSI MONGODB ---
client = MongoClient("mongodb://localhost:27017/")
db = client["kidscare_db"]

# Definisi Blueprint
main_bp = Blueprint('main', __name__)
user_bp = Blueprint('user', __name__, url_prefix='/users')

# --- 2. MAIN ROUTES (LANDING, LOGIN, REGISTER) ---

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
            session['user_id'] = str(user['_id'])
            session['role'] = user.get('role', 'parent')
            session['name'] = user['username']
            return redirect(url_for('user.index'))
        else:
            flash("Email atau Password salah!", "danger")
    return render_template('authentications/login/login.html')

@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
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
            "username": parent_name, "email": contact, "password": hashed_pw,
            "address": address, "role": "parent", "created_at": datetime.utcnow()
        })
        
        birth_date = datetime.strptime(child_birth, '%Y-%m-%d') if child_birth else None
        db.children.insert_one({
            "parent_id": user_result.inserted_id, "name": child_name,
            "birth_date": birth_date, "gender": gender, "created_at": datetime.utcnow()
        })
        flash("Registrasi Berhasil! Silakan Login.", "success")
        return redirect(url_for('main.login'))
    return render_template('authentications/register/register.html')

@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.landing'))

# --- 3. USER ROUTES (DASHBOARD & PROFILE MANAGEMENT) ---

@user_bp.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    user_data = db.users.find_one({"_id": ObjectId(session['user_id'])})
    children = list(db.children.find({"parent_id": ObjectId(session['user_id'])}).sort("created_at", 1))
    default_child = children[0] if children else None
    return render_template('users/index.html', user=user_data, child=default_child, children=children)

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

# --- FITUR SKRINING, EDUKASI & KONSULTASI ---
@user_bp.route('/skrining')
def test_skrining():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    # Menampilkan daftar anak agar orang tua bisa memilih siapa yang akan dites
    children = list(db.children.find({"parent_id": ObjectId(session['user_id'])}))
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
    if 'user_id' not in session: return redirect(url_for('main.login'))
    try:
        child_id = request.form.get('child_id')
        questions = list(db.questions.find().sort("order", 1))
        in_score = hy_score = 0
        additional_met = True
        
        for i, q in enumerate(questions):
            val = request.form.get(f'q{i}')
            if val is None: continue
            score = int(val)
            if q['category'] == 'inattention' and score >= 2: in_score += 1
            elif q['category'] == 'hyperactivity' and score >= 2: hy_score += 1
            elif q['category'] == 'additional' and score == 0: additional_met = False

        category = "Normal / Risiko Rendah"
        if additional_met:
            if in_score >= 6 and hy_score >= 6: category = "ADHD Tipe Campuran"
            elif in_score >= 6: category = "ADHD Tipe Inatensi"
            elif hy_score >= 6: category = "ADHD Tipe Hiperaktif-Impulsivitas"

        # Simpan hasil untuk anak spesifik
        db.screening_tests.insert_one({
            "child_id": ObjectId(child_id), "inattentive_score": in_score,
            "hyperactive_score": hy_score, "category": category, "created_at": datetime.utcnow()
        })
        return render_template('users/testskrining/result.html', result=category, in_score=in_score, hy_score=hy_score)
    except Exception as e:
        return f"Error: {str(e)}"

@user_bp.route('/skrining/riwayat')
def riwayat_skrining():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    children = list(db.children.find({"parent_id": ObjectId(session['user_id'])}).sort("created_at", 1))
    
    selected_child_id = request.args.get('child_id')
    if not selected_child_id and children:
        selected_child_id = str(children[0]['_id'])
    
    history = []
    selected_child = None
    
    if selected_child_id:
        selected_child = db.children.find_one({"_id": ObjectId(selected_child_id)})
        # Ambil riwayat hanya untuk anak yang dipilih
        history = list(db.screening_tests.find({"child_id": ObjectId(selected_child_id)}).sort("created_at", -1))
        
    return render_template('users/riwayatskrining/riwayat_skrining.html', 
                           history=history, 
                           children=children, 
                           selected_child=selected_child)

# --- EDUKASI & KONSULTASI ---
@user_bp.route('/edukasi')
def edukasi_user():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    videos = list(db.videos.find()); return render_template('users/edukasi/edukasi_user.html', videos=videos)

@user_bp.route('/edukasi/<id>')
def edukasi_detail(id):
    if 'user_id' not in session: return redirect(url_for('main.login'))
    video = db.videos.find_one({"_id": ObjectId(id)}); return render_template('users/edukasi/edukasi_detail.html', video=video)

@user_bp.route('/konsultasi')
def konsultasi_psikolog():
    psychologists = [{'name': 'Firda Amalia, M.Psi., Psikolog', 'specialization': 'Anak', 'whatsapp': '628232292269'}]
    return render_template('users/konsultasi/konsultasi_psikolog.html', psychologists=psychologists)

app.register_blueprint(main_bp);
app.register_blueprint(user_bp)

if __name__ == '__main__':
    app.run(debug=True, port=5000)