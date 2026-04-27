from dotenv import load_dotenv
load_dotenv()

from ai_agent import analyze_plant
import json

# Simuler une plante identifiee par PlantNet
plant_info = {
    "scientific_name": "Ipomoea batatas",
    "common_name": "Patate douce",
    "family": "Convolvulaceae",
    "confidence": 48.3
}

print("Test analyze_plant...")
result = analyze_plant(plant_info)
print(json.dumps(result, indent=2, ensure_ascii=False))
