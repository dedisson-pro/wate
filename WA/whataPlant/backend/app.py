from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import os, json, base64, time, uuid

load_dotenv()

from database import init_db, save_scan, get_all_scans, get_scan_by_id, get_dashboard_stats
from plant_service import identify_plant, parse_plantnet_result
from ai_agent import analyze_plant, chat_with_agent

# Chercher le dossier frontend (local ou Railway)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Ordre de priorité : backend/static → ../frontend → dossier courant
for candidate in [
    os.path.join(BASE_DIR, "static"),
    os.path.join(BASE_DIR, "../frontend"),
    BASE_DIR
]:
    if os.path.exists(os.path.join(candidate, "index.html")):
        FRONTEND_DIR = os.path.abspath(candidate)
        break
else:
    FRONTEND_DIR = BASE_DIR

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app, origins=os.getenv("ALLOWED_ORIGINS", "*"))

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

init_db()

# ── SCAN ─────────────────────────────────────────────────────
@app.route("/api/scan", methods=["POST"])
def scan_plant():
    image_bytes = None
    lat, lon = None, None

    if "image" in request.files:
        image_bytes = request.files["image"].read()
        lat = request.form.get("latitude")
        lon = request.form.get("longitude")
    else:
        data = request.get_json(silent=True) or {}
        image_b64 = data.get("image_b64", "")
        if not image_b64:
            return jsonify({"error": "Image manquante"}), 400
        try:
            image_bytes = base64.b64decode(image_b64.split(",")[-1])
        except Exception as e:
            return jsonify({"error": f"Image invalide : {e}"}), 400
        lat = data.get("latitude")
        lon = data.get("longitude")

    img_filename = f"{uuid.uuid4().hex}.jpg"
    with open(os.path.join(UPLOAD_DIR, img_filename), "wb") as f:
        f.write(image_bytes)

    plantnet_raw = identify_plant(image_bytes)
    plant_info = parse_plantnet_result(plantnet_raw)
    if "error" in plant_info:
        return jsonify({"error": plant_info["error"]}), 422

    ai_result = analyze_plant(plant_info)

    # Nettoyer recipe_images pour la sérialisation JSON
    recipe_images = ai_result.get("recipe_images", [])
    ai_result_clean = {k: v for k, v in ai_result.items() if k != "recipe_images"}
    ai_result_clean["recipe_images"] = [
        {"name": r.get("name", ""), "image_url": r.get("image_url")}
        for r in recipe_images
    ]

    scan_data = {
        "image_path": img_filename,
        "common_name": plant_info.get("common_name"),
        "scientific_name": plant_info.get("scientific_name"),
        "family": plant_info.get("family"),
        "confidence": plant_info.get("confidence"),
        "is_edible": ai_result_clean.get("is_edible", "Inconnu"),
        "is_medicinal": ai_result_clean.get("is_medicinal", "Inconnu"),
        "is_toxic": ai_result_clean.get("is_toxic", "Inconnu"),
        "is_invasive": ai_result_clean.get("is_invasive", "Inconnu"),
        "health_status": ai_result_clean.get("health_status", ""),
        "ai_report": json.dumps(ai_result_clean, ensure_ascii=False),
        "plantnet_raw": json.dumps(plantnet_raw, ensure_ascii=False),
        "latitude": float(lat) if lat else None,
        "longitude": float(lon) if lon else None,
    }

    scan_id = save_scan(scan_data)
    return jsonify({
        "scan_id": scan_id,
        "plant": plant_info,
        "analysis": ai_result_clean,
        "image_url": f"/api/image/{img_filename}"
    })

# ── CAMÉRA (local uniquement) ─────────────────────────────────
@app.route("/api/camera/capture", methods=["POST"])
def camera_capture():
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return jsonify({"error": "Caméra non disponible sur ce serveur"}), 400
        time.sleep(0.5)
        frame = None
        for _ in range(5):
            ret, frame = cap.read()
            if not ret:
                cap.release()
                return jsonify({"error": "Impossible de lire la caméra"}), 400
        cap.release()
        from plant_service import preprocess_image
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        processed = preprocess_image(buf.tobytes())
        image_b64 = "data:image/jpeg;base64," + base64.b64encode(processed).decode()
        return jsonify({"image_b64": image_b64})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ── IMAGES UPLOADÉES ─────────────────────────────────────────
@app.route("/api/image/<filename>")
def serve_image(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ── HISTORIQUE ───────────────────────────────────────────────
@app.route("/api/history", methods=["GET"])
def history():
    scans = get_all_scans()
    for s in scans:
        try:
            s["ai_report"] = json.loads(s["ai_report"]) if s["ai_report"] else {}
        except (json.JSONDecodeError, TypeError):
            s["ai_report"] = {}
    return jsonify(scans)

@app.route("/api/scan/<int:scan_id>", methods=["GET"])
def get_scan(scan_id):
    scan = get_scan_by_id(scan_id)
    if not scan:
        return jsonify({"error": "Scan introuvable"}), 404
    try:
        scan["ai_report"] = json.loads(scan["ai_report"]) if scan["ai_report"] else {}
    except (json.JSONDecodeError, TypeError):
        scan["ai_report"] = {}
    return jsonify(scan)

# ── CHAT IA ──────────────────────────────────────────────────
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    scan_id = data.get("scan_id")
    message = data.get("message", "")
    history = data.get("history", [])

    if not scan_id or not message:
        return jsonify({"error": "scan_id et message requis"}), 400

    scan = get_scan_by_id(scan_id)
    if not scan:
        return jsonify({"error": "Scan introuvable"}), 404

    try:
        ai_report = json.loads(scan["ai_report"]) if scan["ai_report"] else {}
    except (json.JSONDecodeError, TypeError):
        ai_report = {}

    plant_context = {
        "scientific_name": scan["scientific_name"],
        "common_name": scan["common_name"],
        "ai_report": json.dumps(ai_report, ensure_ascii=False)
    }
    return jsonify(chat_with_agent(plant_context, message, history))

# ── DASHBOARD ────────────────────────────────────────────────
@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    return jsonify(get_dashboard_stats())

# ── FRONTEND ─────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:path>")
def serve_frontend(path):
    if path.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    full_path = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(full_path):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
