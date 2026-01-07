from flask import Flask, render_template, request, redirect, url_for, Blueprint
import numpy as np
import joblib

app = Flask(__name__,
            template_folder='app/templates',
            static_folder='app/static')

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

# --- User Routes ---
@user_bp.route('/')
def index():
    user = {'name': 'Fadiyah Desi Asmawati'}
    child = {'name': 'Anak Fadiyah', 'age': 5}
    return render_template('users/index.html', user=user, child=child)

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