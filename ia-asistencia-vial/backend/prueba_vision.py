import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

with open("incidente.jpeg", "rb") as f:
    imagen = f.read()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(
            data=imagen,
            mime_type="image/jpeg"
        ),
        """Analiza esta imagen como evidencia de un incidente tecnológico.
        Indica:
        1. Qué observas.
        2. Tipo de incidente.
        3. Posible causa.
        4. Nivel de prioridad: baja, media o alta.
        5. Acción recomendada.

        No inventes información que no pueda inferirse razonablemente de la imagen."""
    ]
)

print(response.text)