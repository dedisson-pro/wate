import os
import json
import requests as http_requests
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY manquante")

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """Tu es WhatAPlant, un agent IA expert en botanique, agronomie et medecine traditionnelle africaine.
Tu analyses les plantes et fournis des rapports complets en francais.
Sois precis et mentionne toujours de consulter un professionnel pour usage medical."""

# ── RECHERCHE D'IMAGES GRATUITE ───────────────────────────────

def search_wikimedia_commons(query: str):
    """Cherche une image sur Wikimedia Commons par mot-cle (gratuit, sans cle)."""
    try:
        resp = http_requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrnamespace": 6,
                "gsrsearch": query,
                "gsrlimit": 3,
                "prop": "imageinfo",
                "iiprop": "url|thumburl",
                "iiurlwidth": 400,
                "format": "json"
            },
            timeout=5
        )
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [])
            if info:
                url = info[0].get("thumburl") or info[0].get("url")
                if url and not url.endswith(".svg"):
                    return url
    except Exception as e:
        print(f"Wikimedia Commons error: {e}")
    return None

def search_wikipedia_image(query: str):
    """Cherche l'image principale d'un article Wikipedia (gratuit, sans cle)."""
    try:
        resp = http_requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": query,
                "prop": "pageimages",
                "format": "json",
                "pithumbsize": 400,
                "redirects": 1
            },
            timeout=5
        )
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {}).get("source")
            if thumb:
                return thumb
    except Exception as e:
        print(f"Wikipedia image error: {e}")
    return None

def get_food_image(recipe_name: str, plant_name: str):
    """
    Cherche une image de recette/plat via plusieurs sources gratuites.
    Ordre : Wikimedia Commons (recette) → Wikipedia (recette) →
            Wikimedia Commons (plante) → Wikipedia (plante)
    """
    # Essayer avec le nom de la recette
    img = search_wikimedia_commons(recipe_name + " food dish")
    if img:
        return img
    img = search_wikipedia_image(recipe_name)
    if img:
        return img
    # Fallback sur la plante elle-meme
    img = search_wikimedia_commons(plant_name + " plant food")
    if img:
        return img
    img = search_wikipedia_image(plant_name)
    if img:
        return img
    return None

# ── ANALYSE PLANTE ────────────────────────────────────────────

def analyze_plant(plant_info: dict) -> dict:
    """Genere un rapport complet sur la plante via Groq + images via Wikimedia."""
    prompt = (
        "Analyse la plante : " + str(plant_info.get("scientific_name")) +
        " (" + str(plant_info.get("common_name")) + "), famille " +
        str(plant_info.get("family")) + ", confiance " +
        str(plant_info.get("confidence")) + "%.\n"
        "Reponds UNIQUEMENT avec ce JSON sans texte avant ou apres :\n"
        '{"health_status":"...","is_edible":"Oui/Non/Partiellement","edible_details":"...",'
        '"recipe_suggestions":["nom recette africaine 1","nom recette africaine 2","nom recette africaine 3"],'
        '"is_medicinal":"Oui/Non","medicinal_details":"...",'
        '"is_toxic":"Oui/Non/Partiellement","toxic_details":"...",'
        '"is_invasive":"Oui/Non","environmental_impact":"...","summary":"..."}'
    )
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        content = response.choices[0].message.content.strip()
        # Nettoyer le markdown si présent
        if "```" in content:
            parts = content.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    content = part
                    break
        # Extraire le JSON si du texte précède
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            content = content[start:end]
        result = json.loads(content)

        # Chercher des images pour chaque recette suggérée
        plant_name = plant_info.get("common_name") or plant_info.get("scientific_name", "plant")
        recipes = result.get("recipe_suggestions", [])
        recipe_images = []
        for recipe in recipes[:3]:
            img_url = get_food_image(recipe, plant_name)
            recipe_images.append({
                "name": recipe,
                "image_url": img_url  # None si aucune image trouvée
            })
        result["recipe_images"] = recipe_images
        return result

    except Exception as e:
        print(f"analyze_plant error: {e}")
        return {
            "error": str(e),
            "summary": "Analyse IA indisponible.",
            "recipe_images": [],
            "is_edible": "Inconnu",
            "is_medicinal": "Inconnu",
            "is_toxic": "Inconnu",
            "is_invasive": "Inconnu",
            "health_status": "",
            "edible_details": "",
            "medicinal_details": "",
            "toxic_details": "",
            "environmental_impact": ""
        }

# ── CHAT AGENT ────────────────────────────────────────────────

def chat_with_agent(plant_context: dict, user_message: str, history: list) -> dict:
    """Conversation contextuelle avec l'agent IA + image si recette demandee."""
    context = (
        "Plante : " + str(plant_context.get("scientific_name")) +
        " (" + str(plant_context.get("common_name")) + "). " +
        "Rapport : " + str(plant_context.get("ai_report", ""))
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context}]
    for msg in history[-6:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.5,
            max_tokens=800
        )
        reply_text = response.choices[0].message.content

        # Chercher une image si l'utilisateur parle de recette/sauce
        recipe_keywords = ["recette", "sauce", "preparer", "cuisiner", "plat",
                           "decoction", "infusion", "comment faire", "manger"]
        image_url = None
        if any(kw in user_message.lower() for kw in recipe_keywords):
            plant_name = plant_context.get("common_name", "plant")
            image_url = get_food_image(user_message[:50], plant_name)

        return {"reply": reply_text, "image_url": image_url}

    except Exception as e:
        return {"reply": "Erreur : " + str(e), "image_url": None}
