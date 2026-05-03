from app import create_app

app = create_app()

if __name__ == '__main__':
    # debug=True agar server otomatis restart kalau kamu save perubahan kode
    app.run(debug=True, host='0.0.0.0', port=5000)