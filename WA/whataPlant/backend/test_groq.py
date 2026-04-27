from dotenv import load_dotenv
load_dotenv()
import os
from groq import Groq

key = os.getenv("GROQ_API_KEY")
print("Cle chargee:", bool(key), "| Debut:", key[:15] if key else "VIDE")

try:
    client = Groq(api_key=key)
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "Reponds juste: OK"}],
        max_tokens=10
    )
    print("Groq OK:", r.choices[0].message.content)
except Exception as e:
    print("Groq ERREUR:", e)
