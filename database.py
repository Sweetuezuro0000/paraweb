import sqlite3
from datetime import datetime


DB_NAME = "paraweb.db"



# ===============================
# DATABASE CONNECT
# ===============================


def connect():

    return sqlite3.connect(
        DB_NAME
    )



# ===============================
# CREATE TABLES
# ===============================


def init_db():

    db = connect()

    cursor = db.cursor()


    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(

        id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        joined TEXT

    )
    """)



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        service TEXT,

        business TEXT,

        features TEXT,

        budget TEXT,

        requirement TEXT,

        contact TEXT,

        status TEXT,

        created TEXT

    )
    """)



    db.commit()

    db.close()



# ===============================
# SAVE USER
# ===============================


def save_user(
    user_id,
    username,
    first_name
):

    db=connect()

    cursor=db.cursor()


    cursor.execute(

    """
    INSERT OR IGNORE INTO users
    VALUES(?,?,?,?)
    """,

    (
        user_id,
        username,
        first_name,
        str(datetime.now())
    )

    )


    db.commit()

    db.close()



# ===============================
# SAVE LEAD
# ===============================


def save_lead(
    user_id,
    data
):

    db=connect()

    cursor=db.cursor()


    cursor.execute(

    """

    INSERT INTO leads

    (
    user_id,
    service,
    business,
    features,
    budget,
    requirement,
    contact,
    status,
    created
    )

    VALUES(?,?,?,?,?,?,?,?,?)

    """,

    (

    user_id,

    data.get("service"),

    data.get("business"),

    str(
        data.get("features")
    ),

    data.get("budget"),

    data.get("requirement"),

    data.get("contact"),

    "NEW",

    str(datetime.now())

    )

    )


    db.commit()

    db.close()



# ===============================
# GET ALL LEADS
# ===============================


def get_leads():

    db=connect()

    cursor=db.cursor()


    cursor.execute(
        "SELECT * FROM leads ORDER BY id DESC"
    )


    data=cursor.fetchall()


    db.close()


    return data



# ===============================
# UPDATE STATUS
# ===============================


def update_status(
    lead_id,
    status
):

    db=connect()

    cursor=db.cursor()


    cursor.execute(

    """
    UPDATE leads
    SET status=?
    WHERE id=?

    """,

    (
        status,
        lead_id
    )

    )


    db.commit()

    db.close()
# ===============================
# GET USERS
# ===============================

def get_users():

    db = connect()

    cursor = db.cursor()

    cursor.execute(
        "SELECT id FROM users"
    )

    users = cursor.fetchall()

    db.close()

    return users
