from flask import Flask, render_template, request, redirect, session, url_for, Blueprint
import numpy as np
import joblib

app = Flask(__name__,
            template_folder='app/templates',
            static_folder='app/static')
app.secret_key = 'kidscare-secret-key-dev'

# Definisi Blueprint
main_bp = Blueprint('main', __name__)
user_bp = Blueprint('user', __name__, url_prefix='/users')

# --- Main Routes ---
@main_bp.route('/')
def landing():
    return render_template('index.html')

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        return redirect(url_for('user.index'))
    return render_template('authentications/login/login.html')

@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        return redirect(url_for('user.index'))
    return render_template('authentications/register/register.html')

# LOGOUT
@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.landing'))

# --- User Routes ---
@user_bp.route('/')
def index():
    user = {'name': 'Fadiyah Desi Asmawati'}
    child = {'name': 'Anak Fadiyah', 'age': 5}
    return render_template('users/index.html', user=user, child=child)

#EDUKASI USER
@user_bp.route('/edukasi')
def edukasi_user():
    return render_template('users/edukasi_user.html')

@user_bp.route('/edukasi/<slug>')
def edukasi_detail(slug):
    edukasi_data = {
        'apa-itu-adhd': {
            'title': 'Apa itu ADHD?',
            'content': 'Lorem ipsum dolor sit amet. Qui reiciendis quaerat et dicta enim eum dolorum numquam et earum ullam. Id voluptates earum ex consequatur illo ut sapiente voluptatem et doloribus delectus aut illo reprehenderit! Et quod deleniti aut ipsum officia aut aliquid galisum ea dolor iure ex dolorem quia et aspernatur fugit. 33 fuga voluptatem aut officia aperiam et optio nesciunt ut explicabo laboriosam sed vero quae. Sit mollitia molestiae aut esse fugit ut omnis accusamus et pariatur ullam eum suscipit Quis. Sit libero dolores aut tempora quidem aut eius doloremque vel deleniti error ut nesciunt praesentium et consequatur eveniet? Est animi quasi et aliquid illo et necessitatibus totam! Aut nihil galisum cum perferendis quam hic corporis molestiae et consequatur nesciunt aut unde voluptas ad inventore deserunt? Eos molestiae neque et laudantium itaque qui labore expedita!'
        },
        'gejala-adhd': {
            'title': 'Gejala ADHD',
            'content': 'Gejala ADHD meliputi sulit fokus, hiperaktif, dan impulsif...'
        },
        'penanganan-adhd': {
            'title': 'Cara Penanganan ADHD',
            'content': 'Penanganan ADHD dapat dilakukan melalui terapi perilaku, pendampingan orang tua...'
        }
    }

    edukasi = edukasi_data.get(slug)

    if not edukasi:
        abort(404)

    return render_template('users/edukasi_detail.html', edukasi=edukasi)

@user_bp.route('/profil')
def profil_user():
    user = {
        'name': 'Fadiyah Desi Asmawati',
        'email': 'fadiyahdesiasmawati@gmail.com',
        'phone': '081234567890',
    }
    return render_template('users/profil_user.html', user=user)

@user_bp.route('/skrining')
def test_skrining():
    return render_template('users/test_skrining.html')

@user_bp.route('/skrining/form')
def skrining_form():
    # 20 Pertanyaan Akurat DSM-5
    questions = [
        "Apakah anak sering gagal memberikan perhatian pada rincian?",
        "Apakah anak sering kesulitan mempertahankan perhatian?",
        "Apakah anak sering tampak tidak mendengarkan?",
        "Apakah anak sering tidak mengikuti instruksi?",
        "Apakah anak sering kesulitan mengatur tugas?",
        "Apakah anak sering menghindari tugas konsentrasi lama?",
        "Apakah anak sering kehilangan barang penting?",
        "Apakah anak sering mudah teralihkan?",
        "Apakah anak sering pelupa dalam rutin harian?",
        "Apakah anak sering gelisah (tangan/kaki)?",
        "Apakah anak sering meninggalkan tempat duduk?",
        "Apakah anak sering berlari/memanjat berlebihan?",
        "Apakah anak sering kesulitan bermain tenang?",
        "Apakah anak sering sangat aktif ('mesin')?",
        "Apakah anak sering bicara berlebihan?",
        "Apakah anak sering menjawab sebelum selesai?",
        "Apakah anak sering sulit menunggu giliran?",
        "Apakah anak sering menyela orang lain?",
        "Apakah perilaku muncul sebelum usia 12 tahun?",
        "Apakah perilaku muncul di 2 tempat atau lebih?"
    ]
    return render_template('users/skrining_form.html', questions=questions)

@user_bp.route('/skrining/riwayat')
def riwayat_skrining():
    return render_template('users/riwayat_skrining.html')

@user_bp.route('/predict', methods=['POST'])
def predict():
    try:
        # Mengambil 20 jawaban (q0 - q19)
        answers = []
        for i in range(20):
            val = request.form.get(f'q{i}')
            if val is not None:
                answers.append(int(val))
        
        # Logika analisis sederhana (akan diganti dengan load .pkl nantinya)
        total_score = sum(answers)
        prediction = 1 if total_score >= 30 else 0
        confidence = 94.5
        
        result_text = "Berisiko ADHD" if prediction == 1 else "Tidak Berisiko ADHD"
        
        return render_template('users/result.html', 
                               result=result_text, 
                               confidence=confidence, 
                               prediction=prediction)
    except Exception as e:
        return f"Terjadi kesalahan: {str(e)}"

# Registrasi Blueprint
app.register_blueprint(main_bp)
app.register_blueprint(user_bp)

if __name__ == '__main__':
    app.run(debug=True, port=5000)