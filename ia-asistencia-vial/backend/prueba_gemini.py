import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

print("¿Clave cargada?:", bool(os.getenv("GEMINI_API_KEY")))

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Responde únicamente: Conexión con Gemini exitosa."
)

print(response.text)