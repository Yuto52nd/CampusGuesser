import math
import os
import random
import sqlite3

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    g,
)  # type: ignore

from werkzeug.utils import secure_filename  # type: ignore


# =========================================================
# FLASK APP CONFIGURATION
# =========================================================

app = Flask(__name__)

# Secret key for Flask sessions
app.secret_key = "dev"

# Database file
DATABASE = "game.db"

# Maximum number of rounds per game
MAX_ROUNDS = 5

# Folder where uploaded images are stored
UPLOAD_FOLDER = "static/images"

# Allowed image file extensions
ALLOWED_EXTENSIONS = {"jpg"}

# Flask upload folder configuration
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# =========================================================
# CHALLENGE PRESETS
# =========================================================
# Each challenge contains a list of location IDs

CHALLENGES = {
    1: [1, 9, 10, 11, 212, 238, 253, 254, 255, 256, 257, 258, 259, 260, 278, 279],
    2: [],
}


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def allowed_file(filename):
    """
    Checks whether the uploaded file has an allowed extension.
    """
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def get_db():
    """
    Creates a database connection if one does not already exist
    for the current request.
    """
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row

    return g.db


def eucal(lat1, lon1, lat2, lon2):
    """
    Calculates approximate Euclidean distance in meters
    between two latitude/longitude coordinates.
    """

    meters_per_deg_lat = 111320

    # Average latitude used to adjust longitude scaling
    avg_lat = math.radians((lat1 + lat2) / 2)

    meters_per_deg_lon = meters_per_deg_lat * math.cos(avg_lat)

    # Distance differences
    dx = (lon2 - lon1) * meters_per_deg_lon
    dy = (lat2 - lat1) * meters_per_deg_lat

    return math.sqrt(dx**2 + dy**2)


# =========================================================
# DATABASE CLEANUP
# =========================================================

@app.teardown_appcontext
def close_db(error):
    """
    Closes the database connection after each request.
    """

    db = g.pop("db", None)

    if db is not None:
        db.close()


# =========================================================
# HOME PAGE / GAME RESET
# =========================================================

@app.route("/")
def home():
    """
    Starts a brand new game session.
    """

    session.clear()

    session.update({
        "score": 0,
        "round": 0,
        "used_ids": [],
    })

    return render_template("home.html")


# =========================================================
# OVERVIEW PAGE
# =========================================================

@app.route("/overview")
def overview():
    """
    Displays all locations currently stored in the database.
    """

    db = get_db()

    locations = db.execute(
        "SELECT * FROM locations"
    ).fetchall()

    return render_template(
        "overview.html",
        locations=locations,
    )


# =========================================================
# ADD NEW LOCATION
# =========================================================

@app.route("/add", methods=["GET", "POST"])
def add_location():
    """
    Adds a new location and image to the database.
    """

    if request.method == "POST":

        # Get form data
        file = request.files.get("image")
        lat = request.form.get("lat")
        lng = request.form.get("lng")
        description = request.form.get("description")

        # Ensure file exists
        if not file or file.filename == "":
            return "No file selected", 400

        # Ensure uploaded file is JPG
        if not allowed_file(file.filename):
            return "Only JPG files allowed", 400

        # Generate unique filename
        import uuid

        filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"

        # Save file to upload folder
        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename,
        )

        file.save(filepath)

        # Insert into database
        db = get_db()

        db.execute(
            """
            INSERT INTO locations (image, lat, lng, description)
            VALUES (?, ?, ?, ?)
            """,
            (filename, lat, lng, description),
        )

        db.commit()

        return redirect(url_for("overview"))

    return render_template("add.html")


# =========================================================
# DELETE LOCATION
# =========================================================

@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    """
    Deletes a location from the database
    and removes its image file.
    """

    db = get_db()

    # Get image filename
    loc = db.execute(
        "SELECT image FROM locations WHERE id = ?",
        (id,),
    ).fetchone()

    # Delete image file if it exists
    if loc:
        try:
            os.remove(
                os.path.join(
                    "static/images",
                    loc["image"],
                )
            )
        except:
            pass

    # Delete database row
    db.execute(
        "DELETE FROM locations WHERE id = ?",
        (id,),
    )

    db.commit()

    return redirect(url_for("overview"))


# =========================================================
# MAIN GAME ROUTE
# =========================================================

@app.route("/CGGAME")
def CGGAME():
    """
    Runs the main game logic and selects
    the next location.
    """

    # End game if max rounds reached
    if session.get("round", 0) >= MAX_ROUNDS:
        return redirect(url_for("final_score"))

    db = get_db()

    challenge_ids = session.get("challenge_ids")
    used_ids = session.get("used_ids", [])

    # =====================================================
    # CHALLENGE / MULTIPLAYER MODE
    # =====================================================

    if challenge_ids:

        # Remaining unused challenge locations
        remaining = [
            i for i in challenge_ids
            if i not in used_ids
        ]

        if not remaining:
            return redirect(url_for("final_score"))

        # Select random remaining location
        location_id = remaining[0]
        location_id = random.choice(remaining)

        # Fetch selected location
        location = db.execute(
            "SELECT * FROM locations WHERE id = ?",
            (location_id,),
        ).fetchone()

    # =====================================================
    # NORMAL GAME MODE
    # =====================================================

    else:

        # Exclude already used locations
        if used_ids:

            placeholders = ",".join("?" * len(used_ids))

            query = f"""
                SELECT * FROM locations
                WHERE id NOT IN ({placeholders})
                ORDER BY RANDOM()
                LIMIT 1
            """

            location = db.execute(
                query,
                used_ids,
            ).fetchone()

        # First round
        else:

            location = db.execute(
                """
                SELECT * FROM locations
                ORDER BY RANDOM()
                LIMIT 1
                """
            ).fetchone()

    # No locations left
    if not location:
        return redirect(url_for("final_score"))

    # Track used location IDs
    session["used_ids"].append(location["id"])

    # Store current location ID
    session["current_id"] = location["id"]

    return render_template(
        "CGGAME.html",
        image=location["image"],
        score=session["score"],
        round=session["round"] + 1,
        max_rounds=MAX_ROUNDS,
    )


# =========================================================
# GUESS SUBMISSION
# =========================================================

@app.route("/guess", methods=["GET", "POST"])
@app.route("/guess", methods=["GET", "POST"], endpoint="campus_guesser")
@app.route("/guess", methods=["POST"])
def guess():
    """
    Handles player guesses and calculates score.
    """

    lat_str = request.form.get("lat")
    lng_str = request.form.get("lng")

    # Ensure guess exists
    if not lat_str or not lng_str:
        return redirect(url_for("CGGAME"))

    # Convert to float
    lat = float(lat_str)
    lng = float(lng_str)

    db = get_db()

    # Get current location
    location = db.execute(
        "SELECT * FROM locations WHERE id = ?",
        (session["current_id"],),
    ).fetchone()

    # Calculate distance
    distance = eucal(
        lat,
        lng,
        location["lat"],
        location["lng"],
    )

    # Calculate score
    score_add = min(
        max(0, int(5050 - distance * 10)),
        5000,
    )

    # Update session values
    session["score"] += score_add
    session["round"] += 1

    return render_template(
        "results.html",
        image=location["image"],
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


# =========================================================
# CHALLENGE SELECTION PAGE
# =========================================================

@app.route("/challenges")
def challenges():
    """
    Displays available challenges.
    """

    return render_template("challenges.html")


# =========================================================
# START PRESET CHALLENGE
# =========================================================

@app.route("/start_challenge/<int:challenge_id>")
def start_challenge(challenge_id):
    """
    Starts a predefined challenge.
    """

    if challenge_id not in CHALLENGES:
        return "Challenge not found", 404

    session.clear()

    session["score"] = 0
    session["round"] = 0
    session["challenge_ids"] = CHALLENGES[challenge_id]
    session["used_ids"] = []
    session["multiplayer_mode"] = False

    return redirect(url_for("CGGAME"))


# =========================================================
# START MULTIPLAYER MATCH
# =========================================================

@app.route("/start_multiplayer")
def start_multiplayer():
    """
    Creates a multiplayer challenge
    with random locations.
    """

    db = get_db()

    rows = db.execute(
        """
        SELECT id FROM locations
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (MAX_ROUNDS,),
    ).fetchall()

    # Ensure enough locations exist
    if len(rows) < MAX_ROUNDS:
        return "Not enough locations to start multiplayer match", 400

    challenge_ids = [row["id"] for row in rows]

    session.clear()

    session["score"] = 0
    session["round"] = 0
    session["challenge_ids"] = challenge_ids
    session["used_ids"] = []
    session["multiplayer_mode"] = True

    return redirect(url_for("CGGAME"))


# =========================================================
# MULTIPLAYER SHARE LINK
# =========================================================

@app.route("/multiplayer/<path:ids>")
def multiplayer_link(ids):
    """
    Loads a multiplayer game using shared IDs.
    """

    # Convert IDs from URL into integers
    try:
        challenge_ids = [
            int(i)
            for i in ids.split(",")
            if i
        ]

    except ValueError:
        return "Invalid multiplayer link", 400

    # Ensure correct number of rounds
    if len(challenge_ids) != MAX_ROUNDS:
        return "Invalid multiplayer match", 400

    db = get_db()

    placeholders = ",".join("?" * len(challenge_ids))

    # Validate IDs exist
    valid_rows = db.execute(
        f"""
        SELECT id FROM locations
        WHERE id IN ({placeholders})
        """,
        challenge_ids,
    ).fetchall()

    if len(valid_rows) != len(challenge_ids):
        return "Invalid multiplayer match", 404

    # Optional comparison score
    shared_score = request.args.get("score")

    # Reset session
    session.clear()

    session["score"] = 0
    session["round"] = 0
    session["challenge_ids"] = challenge_ids
    session["used_ids"] = []
    session["multiplayer_mode"] = True
    session["shared_score"] = shared_score

    return render_template(
        "multiplayer.html",
        ids_str=ids,
        shared_score=shared_score,
        max_rounds=MAX_ROUNDS,
    )


# =========================================================
# FINAL SCORE PAGE
# =========================================================

@app.route("/final")
def final_score():
    """
    Displays final score and multiplayer share link.
    """

    share_url = None

    # Generate multiplayer share link
    if (
        session.get("multiplayer_mode")
        and session.get("challenge_ids")
    ):

        ids = ",".join(
            str(i)
            for i in session["challenge_ids"]
        )

        share_url = url_for(
            "multiplayer_link",
            ids=ids,
            score=session["score"],
            _external=True,
        )

    return render_template(
        "final.html",
        score=session["score"],
        share_url=share_url,
    )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)