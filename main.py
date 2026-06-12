import sqlite3
import json
import hashlib
import time
from itertools import combinations
from collections import Counter

DB_FILE = "lineups.db"


# ============================================================
# DB
# ============================================================


def db():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS features(
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS players(
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS player_features(
        player_id INTEGER NOT NULL,
        feature_id INTEGER NOT NULL,
        PRIMARY KEY(player_id, feature_id)
    );
    CREATE TABLE IF NOT EXISTS templates(
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS template_positions(
        id INTEGER PRIMARY KEY,
        template_id INTEGER NOT NULL,
        position_no INTEGER NOT NULL,
        feature_id INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS cached_runs(
        cache_key TEXT PRIMARY KEY,
        template_id INTEGER NOT NULL,
        setup_count INTEGER NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS cached_setups(
        cache_key TEXT NOT NULL,
        setup_no INTEGER NOT NULL,
        setup_json TEXT NOT NULL,
        PRIMARY KEY(cache_key, setup_no)
    );
    CREATE TABLE IF NOT EXISTS player_exclusions(
        player1_id INTEGER NOT NULL,
        player2_id INTEGER NOT NULL,
        PRIMARY KEY(player1_id, player2_id)
    );
    CREATE TABLE IF NOT EXISTS player_groups(
        player_id INTEGER PRIMARY KEY,
        group_name TEXT NOT NULL
    )
    """)

    conn.commit()

    for feature in ["prop", "jumper", "not_prop", "ball_taker"]:
        cur.execute("INSERT OR IGNORE INTO features(name) VALUES(?)", (feature,))
    conn.commit()
    conn.close()


# ============================================================
# FEATURES
# ============================================================


def list_features():
    conn = db()
    cur = conn.cursor()

    rows = cur.execute("SELECT id,name FROM features ORDER BY name").fetchall()

    conn.close()
    return rows


def add_feature():
    show_features()
    name = input("Feature name: ").strip()

    conn = db()
    cur = conn.cursor()

    cur.execute("INSERT INTO features(name) VALUES(?)", (name,))

    conn.commit()
    conn.close()


def show_features():
    rows = list_features()

    print("\nFeatures:")
    for fid, name in rows:
        print(f"{fid}: {name}")


# ============================================================
# PLAYERS
# ============================================================


def list_players():
    conn = db()
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT p.id, p.name
        FROM players p
        ORDER BY p.name
    """).fetchall()

    conn.close()
    return rows


def add_player():
    show_players()
    features = list_features()

    print("\nFeatures:")
    for fid, name in features:
        print(f"{fid}: {name}")

    player_name = input("\nPlayer name: ").strip()

    ids = input("Feature ids (comma separated): ").strip()

    selected = [int(x.strip()) for x in ids.split(",") if x.strip()]

    conn = db()
    cur = conn.cursor()

    cur.execute("INSERT INTO players(name) VALUES(?)", (player_name,))

    player_id = cur.lastrowid

    for fid in selected:
        cur.execute(
            """
            INSERT INTO player_features(
                player_id,
                feature_id
            )
            VALUES(?,?)
            """,
            (player_id, fid),
        )

    conn.commit()
    conn.close()


def show_players():
    rows = list_players()

    if not rows:
        print("\nNo players.\n")
        return

    print("\nPlayers:")
    for pid, name in rows:
        print(f"{pid}: {name}")


def add_exclusion():
    show_players()

    p1 = int(input("\nPlayer 1 id: "))
    p2 = int(input("Player 2 id: "))

    if p1 == p2:
        print("Cannot exclude player from himself.")
        return

    a, b = sorted([p1, p2])

    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR IGNORE INTO player_exclusions(
            player1_id,
            player2_id
        )
        VALUES (?, ?)
    """,
        (a, b),
    )

    conn.commit()
    conn.close()


def load_exclusions():
    conn = db()
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT player1_id, player2_id
        FROM player_exclusions
    """).fetchall()

    conn.close()

    return {tuple(sorted((a, b))) for a, b in rows}


# ============================================================
# TEMPLATES
# ============================================================


def add_template():
    show_templates()
    name = input("Template name: ").strip()
    count = int(input("Positions count: "))

    features = list_features()

    print("\nFeatures:")
    for fid, fname in features:
        print(f"{fid}: {fname}")

    conn = db()
    cur = conn.cursor()

    cur.execute("INSERT INTO templates(name) VALUES(?)", (name,))

    template_id = cur.lastrowid

    for pos in range(1, count + 1):
        fid = int(input(f"Position {pos} feature id: "))

        cur.execute(
            """
            INSERT INTO template_positions(
                template_id,
                position_no,
                feature_id
            )
            VALUES(?,?,?)
            """,
            (template_id, pos, fid),
        )

    conn.commit()
    conn.close()


def show_templates():
    conn = db()
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT id, name
        FROM templates
        ORDER BY name
    """).fetchall()

    conn.close()

    print("\nTemplates:")
    for tid, name in rows:
        print(f"{tid}: {name}")


# ============================================================
# CACHE HASH
# ============================================================


def build_player_hash():
    conn = db()
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT
            p.name,
            f.name
        FROM players p
        JOIN player_features pf
            ON pf.player_id = p.id
        JOIN features f
            ON f.id = pf.feature_id
        ORDER BY p.name, f.name
    """).fetchall()

    grouped = {}

    for player, feature in rows:
        grouped.setdefault(player, []).append(feature)

    canonical = []

    for player in sorted(grouped):
        canonical.append(f"{player}|{','.join(sorted(grouped[player]))}")

    rows = cur.execute("""
        SELECT player1_id, player2_id
        FROM player_exclusions
        ORDER BY player1_id, player2_id
    """).fetchall()

    conn.close()

    canonical.append("EXCLUSIONS")

    for a, b in rows:
        canonical.append(f"{a}:{b}")

    payload = "\n".join(canonical)

    return hashlib.sha256(payload.encode()).hexdigest()


# ============================================================
# LOAD DATA
# ============================================================


def load_players():
    conn = db()
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT
            p.id,
            p.name,
            f.name
        FROM players p
        JOIN player_features pf
            ON p.id = pf.player_id
        JOIN features f
            ON f.id = pf.feature_id
    """).fetchall()

    conn.close()

    players = {}

    for pid, name, feature in rows:
        players.setdefault(pid, {"id": pid, "name": name, "features": set()})

        players[pid]["features"].add(feature)

    return list(players.values())


def load_template(template_id):
    conn = db()
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT f.name
        FROM template_positions tp
        JOIN features f
            ON f.id = tp.feature_id
        WHERE tp.template_id = ?
        ORDER BY tp.position_no
    """,
        (template_id,),
    ).fetchall()

    conn.close()

    return [x[0] for x in rows]


# ============================================================
# SOLVER
# ============================================================


def find_setups(template_id):
    player_hash = build_player_hash()
    cache_key = f"{template_id}:{player_hash}"

    conn = db()
    cur = conn.cursor()

    cached = cur.execute(
        """
        SELECT setup_count
        FROM cached_runs
        WHERE cache_key = ?
    """,
        (cache_key,),
    ).fetchone()

    if cached:
        print("\nUsing cached result.")

        rows = cur.execute(
            """
            SELECT setup_json
            FROM cached_setups
            WHERE cache_key = ?
            ORDER BY setup_no
        """,
            (cache_key,),
        ).fetchall()

        conn.close()

        return [json.loads(row[0]) for row in rows]

    players = load_players()
    exclusions = load_exclusions()
    template = load_template(template_id)

    grouped = Counter(template)

    eligible = {}

    for feature in grouped:
        eligible[feature] = [p for p in players if feature in p["features"]]

    groups = sorted(grouped.items(), key=lambda x: len(eligible[x[0]]))

    results = []

    def dfs(index, used_ids, current):
        if index == len(groups):
            results.append({k: sorted(v) for k, v in current.items()})
            return

        feature, amount = groups[index]

        available = [p for p in eligible[feature] if p["id"] not in used_ids]

        if len(available) < amount:
            return

        for combo in combinations(available, amount):
            new_used = used_ids.copy()

            valid = True

            for p in combo:
                if is_excluded(p["id"], used_ids):
                    valid = False
                    break
                new_used.add(p["id"])

            if not valid:
                continue

            # Check exclusions inside the combo itself
            combo_ids = [p["id"] for p in combo]

            for i in range(len(combo_ids)):
                for j in range(i + 1, len(combo_ids)):
                    pair = tuple(sorted((combo_ids[i], combo_ids[j])))

                    if pair in exclusions:
                        valid = False
                        break

                if not valid:
                    break

            if not valid:
                continue

            new_used = used_ids.copy()

            for p in combo:
                new_used.add(p["id"])

            current[feature] = [p["name"] for p in combo]

            dfs(index + 1, new_used, current)

            del current[feature]

    def is_excluded(player_id, used_ids):
        for uid in used_ids:
            if tuple(sorted((player_id, uid))) in exclusions:
                return True
        return False

    dfs(0, set(), {})

    cur.execute(
        """
        INSERT INTO cached_runs(
            cache_key,
            template_id,
            setup_count,
            created_at
        )
        VALUES(?,?,?,?)
    """,
        (cache_key, template_id, len(results), int(time.time())),
    )

    for idx, setup in enumerate(results):
        cur.execute(
            """
            INSERT INTO cached_setups(
                cache_key,
                setup_no,
                setup_json
            )
            VALUES(?,?,?)
        """,
            (cache_key, idx, json.dumps(setup)),
        )

    conn.commit()
    conn.close()

    return results


# ============================================================
# MENU
# ============================================================


def choose_template():
    conn = db()
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT id,name
        FROM templates
        ORDER BY name
    """).fetchall()

    conn.close()

    if not rows:
        print("No templates.")
        return None

    print()

    for tid, name in rows:
        print(f"{tid}: {name}")

    return int(input("\nTemplate id: "))


def run_template():
    template_id = choose_template()

    if template_id is None:
        return

    setups = find_setups(template_id)

    print(f"\nFound {len(setups)} setup(s)\n")

    for i, setup in enumerate(setups, start=1):
        print(f"Setup #{i}")

        for feature, names in setup.items():
            print(f"  {feature}: " + ", ".join(names))

        print()


def menu():
    while True:
        print("""
1. Add feature
2. Add player
3. Add template
4. Add exclusions
5. Find setups
6. Exit
""")

        choice = input("> ").strip()

        if choice == "1":
            add_feature()

        elif choice == "2":
            add_player()

        elif choice == "3":
            add_template()

        elif choice == "4":
            add_exclusion()

        elif choice == "5":
            run_template()

        elif choice == "6":
            break


if __name__ == "__main__":
    init_db()
    menu()
