from flask import Blueprint, jsonify, request

# Membuat blueprint dengan nama 'main'
main = Blueprint('main', __name__)

# Endpoint 1: Untuk cek apakah server nyala (bisa dicek di browser)
@main.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "success",
        "message": "Halo Amrull! Backend LITERA-DASH sudah nyala dan siap!"
    })

# Endpoint 2: Simulasi menerima data tulisan dari Flutter (POST)
@main.route('/api/cek-tulisan', methods=['POST'])
def cek_tulisan():
    # Nanti data array koordinat (x,y) dari Flutter masuk lewat sini
    data_dari_flutter = request.get_json()
    
    # (Di sini nanti kita taruh logika AI LSTM-nya)
    
    # Kembalikan respon ke Flutter
    return jsonify({
        "status": "success",
        "pesan": "Data goresan berhasil diterima server!",
        "akurasi_sementara": 0.95
    })