import math
import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, g
from werkzeug.utils import secure_filename
import random

app = Flask(__name__)
app.secret_key = "dev"
DATABASE = "game.db"
MAX_ROUNDS = 5
UPLOAD_FOLDER = "static/images"
ALLOWED_EXTENSIONS = {"jpg"}
CHALLENGES = {
    1: [1, 2, 3, 4, 5],
}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
ALLOWED_EXTENSIONS = {"jpg"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/add", methods=["GET", "POST"])
def add_location():
    if request.method == "POST":
        file = request.files.get("image")
        lat = request.form.get("lat")
        lng = request.form.get("lng")
        description = request.form.get("description")

        if not file or file.filename == "":
            return "No file selected", 400

        if not allowed_file(file.filename):
            return "Only JPG files allowed", 400

        import uuid
        filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        db = get_db()
        db.execute(
            "INSERT INTO locations (image, lat, lng, description) VALUES (?, ?, ?, ?)",
            (filename, lat, lng, description), 
        )
        db.commit()

        return redirect(url_for("overview"))

    return render_template("add.html")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    db = get_db()

    # delete image file too
    loc = db.execute("SELECT image FROM locations WHERE id = ?", (id,)).fetchone()

    if loc:
        try:
            os.remove(os.path.join("static/images", loc["image"]))
        except:
            pass

    db.execute("DELETE FROM locations WHERE id = ?", (id,))
    db.commit()

    return redirect(url_for("overview"))



@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

# starts the game a new
@app.route("/")
def home():
    session.clear()
    session.update({"score": 0, "round": 0, "used_ids": []})
    return render_template("home.html")

#runs the overview page 
@app.route("/overview")
def overview():
    db = get_db()
    locations = db.execute("SELECT * FROM locations").fetchall()
    return render_template("overview.html", locations=locations)

@app.route("/CGGAME")
def CGGAME():
    if session.get("round", 0) >= MAX_ROUNDS:
        return redirect(url_for("final_score"))

    db = get_db()

    challenge_ids = session.get("challenge_ids")
    used_ids = session.get("used_ids", [])

    #CHALLENGE MODE
    if challenge_ids:
        remaining = [i for i in challenge_ids if i not in used_ids]

        if not remaining:
            return redirect(url_for("final_score"))
        
        location_id = remaining[0]  
        location_id = random.choice(remaining)

        location = db.execute(
            "SELECT * FROM locations WHERE id = ?", (location_id,)
        ).fetchone()

    
    else:
        if used_ids:
            placeholders = ",".join("?" * len(used_ids))
            query = f"""
                SELECT * FROM locations
                WHERE id NOT IN ({placeholders})
                ORDER BY RANDOM()
                LIMIT 1
            """
            location = db.execute(query, used_ids).fetchone()
        else:
            location = db.execute(
                "SELECT * FROM locations ORDER BY RANDOM() LIMIT 1"
            ).fetchone()

    if not location:
        return redirect(url_for("final_score"))

    # Track used locations
    session["used_ids"].append(location["id"])
    session["current_id"] = location["id"]

    return render_template(
        "CGGAME.html",
        image=location["image"],
        score=session["score"],
        round=session["round"] + 1,
        max_rounds=MAX_ROUNDS,
    )

@app.route("/guess", methods=["GET", "POST"]) 
@app.route("/guess", methods=["GET", "POST"], endpoint="campus_guesser") 
@app.route("/guess", methods=["POST"])
def guess():
    lat_str, lng_str = request.form.get("lat"), request.form.get("lng")
    if not lat_str or not lng_str:
        return redirect(url_for("CGGAME"))

    lat, lng = float(lat_str), float(lng_str)

    db = get_db()
    location = db.execute(
        "SELECT * FROM locations WHERE id = ?", (session["current_id"],)
    ).fetchone()

    distance = eucal(lat, lng, location["lat"], location["lng"])
    score_add = min(max(0, int(5050 - distance * 10)), 5000)
    session["score"] += score_add
    session["round"] += 1

    return render_template(
        "results.html",
        image=location['image'],
        description=location["description"],
        correct_lat=location["lat"],
        correct_lng=location["lng"],
        user_lat=lat,
        user_lng=lng,
        score_add=score_add,
        total_score=session["score"],
        distance=round(distance, 2),
        round=session["round"],
        max_rounds=MAX_ROUNDS,
    )


@app.route("/challenges")
def challenges():
    return render_template("challenges.html")

@app.route("/start_challenge/<int:challenge_id>")
def start_challenge(challenge_id):
    if challenge_id not in CHALLENGES:
        return "Challenge not found", 404

    session.clear()
    session["score"] = 0
    session["round"] = 0
    session["challenge_ids"] = CHALLENGES[challenge_id]
    session["used_ids"] = []

    return redirect(url_for("CGGAME"))


#takes to final page
@app.route("/final")
def final_score():
    return render_template("final.html", score=session["score"])

#Euclidian distance 
def eucal(lat1, lon1, lat2, lon2):
    meters_per_deg_lat = 111320
    avg_lat = math.radians((lat1 + lat2) / 2)
    meters_per_deg_lon = meters_per_deg_lat * math.cos(avg_lat)
    dx = (lon2 - lon1) * meters_per_deg_lon
    dy = (lat2 - lat1) * meters_per_deg_lat
    return math.sqrt(dx**2 + dy**2)


if __name__ == "__main__":
    app.run(debug=True)

