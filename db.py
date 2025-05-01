import sqlite3
import os
import json
from datetime import datetime

DB_FILE = "summaries.db"

def init_db():
    """Initialize the database if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        text_length INTEGER NOT NULL,
        summary TEXT NOT NULL,
        tags TEXT
    )
    ''')
    conn.commit()
    conn.close()

def save_summary_to_db(filename, text_length, summary, tags=""):
    """Save a summary to the database."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute(
        "INSERT INTO summaries (filename, timestamp, text_length, summary, tags) VALUES (?, ?, ?, ?, ?)",
        (filename, timestamp, text_length, summary, tags)
    )
    
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    
    return timestamp, last_id

def get_all_summaries(sort_by="timestamp", sort_order="DESC", search_term=""):
    """Get all summaries from the database with sorting and filtering options."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Validate sort_by to prevent SQL injection
    valid_columns = ["id", "filename", "timestamp", "text_length"]
    if sort_by not in valid_columns:
        sort_by = "timestamp"
    
    # Validate sort_order
    if sort_order.upper() not in ["ASC", "DESC"]:
        sort_order = "DESC"
    
    if search_term:
        # Search in filename and summary
        query = f"""
        SELECT * FROM summaries 
        WHERE filename LIKE ? OR summary LIKE ? OR tags LIKE ?
        ORDER BY {sort_by} {sort_order}
        """
        search_pattern = f"%{search_term}%"
        cursor.execute(query, (search_pattern, search_pattern, search_pattern))
    else:
        query = f"SELECT * FROM summaries ORDER BY {sort_by} {sort_order}"
        cursor.execute(query)
    
    rows = cursor.fetchall()
    
    summaries = []
    for row in rows:
        summaries.append({
            "id": row["id"],
            "filename": row["filename"],
            "timestamp": row["timestamp"],
            "text_length": row["text_length"],
            "summary": row["summary"],
            "tags": row["tags"] if "tags" in row.keys() else ""
        })
    
    conn.close()
    return summaries

def update_summary_tags(summary_id, tags):
    """Update the tags for a summary."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("UPDATE summaries SET tags = ? WHERE id = ?", (tags, summary_id))
    
    conn.commit()
    conn.close()

def delete_summary(summary_id):
    """Delete a summary from the database by ID."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM summaries WHERE id = ?", (summary_id,))
    rows_affected = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    return rows_affected > 0

def delete_all_summaries():
    """Delete all summaries from the database."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM summaries")
    rows_affected = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    return rows_affected 