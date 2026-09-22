import os
from dotenv import load_dotenv
from app import create_app

load_dotenv(override=True)

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)