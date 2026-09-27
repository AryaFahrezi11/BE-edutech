import os
from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)
for model in client.models.list():
    print(model.name)
