from werkzeug.security import generate_password_hash
from pymongo import MongoClient

# Sesuaikan dengan koneksi database Anda
client = MongoClient("mongodb://localhost:27017/") 
db = client['kidscare_db'] # Ganti dengan nama database Anda

# Update password
new_password_hash = generate_password_hash('desi123')
db.users.update_one(
    {"email": "supportkidscare@gmail.com"}, 
    {"$set": {"password": new_password_hash}}
)
print("Password berhasil direset ke: desi123")