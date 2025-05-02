import sqlite3
import os
import json
from datetime import datetime

DB_FILE = "summaries.db"

def init_db():
    """Initialize the database if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if summaries table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='summaries'")
    summaries_exists = cursor.fetchone() is not None
    
    if summaries_exists:
        # Check if batch_id column exists in summaries table
        cursor.execute("PRAGMA table_info(summaries)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "batch_id" not in columns:
            # Add batch_id column to existing table
            cursor.execute("ALTER TABLE summaries ADD COLUMN batch_id INTEGER DEFAULT 1")
            conn.commit()
            print("Added batch_id column to existing summaries table")
    else:
        # Create summaries table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            text_length INTEGER NOT NULL,
            summary TEXT NOT NULL,
            tags TEXT,
            batch_id INTEGER DEFAULT 1
        )
        ''')
    
    # Check if batches table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='batches'")
    if cursor.fetchone() is None:
        # Create batches table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            description TEXT
        )
        ''')
    
    # Create default batch if none exists
    cursor.execute("SELECT COUNT(*) FROM batches")
    if cursor.fetchone()[0] == 0:
        default_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO batches (name, timestamp, description) VALUES (?, ?, ?)",
                     ("Default Batch", default_timestamp, "Default batch for summaries"))
    
    conn.commit()
    conn.close()

def create_batch(name, description=""):
    """Create a new batch."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute(
        "INSERT INTO batches (name, timestamp, description) VALUES (?, ?, ?)",
        (name, timestamp, description)
    )
    
    conn.commit()
    batch_id = cursor.lastrowid
    conn.close()
    
    return batch_id

def get_all_batches():
    """Get all batches."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM batches ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    
    batches = []
    for row in rows:
        # Count summaries in this batch (with error handling)
        try:
            cursor.execute("SELECT COUNT(*) FROM summaries WHERE batch_id = ?", (row["id"],))
            count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            # If batch_id column doesn't exist yet
            count = 0
        
        batches.append({
            "id": row["id"],
            "name": row["name"],
            "timestamp": row["timestamp"],
            "description": row["description"],
            "summary_count": count
        })
    
    conn.close()
    return batches

def delete_batch(batch_id):
    """Delete a batch and all its summaries."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Delete all summaries in the batch
    cursor.execute("DELETE FROM summaries WHERE batch_id = ?", (batch_id,))
    
    # Delete the batch
    cursor.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
    
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return rows_affected > 0

def update_batch(batch_id, name, description):
    """Update batch information."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("UPDATE batches SET name = ?, description = ? WHERE id = ?", 
                 (name, description, batch_id))
    
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return rows_affected > 0

def save_summary_to_db(filename, text_length, summary, tags="", batch_id=1):
    """Save a summary to the database."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute(
        "INSERT INTO summaries (filename, timestamp, text_length, summary, tags, batch_id) VALUES (?, ?, ?, ?, ?, ?)",
        (filename, timestamp, text_length, summary, tags, batch_id)
    )
    
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    
    return timestamp, last_id

def move_summary_to_batch(summary_id, batch_id):
    """Move a summary to a different batch."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("UPDATE summaries SET batch_id = ? WHERE id = ?", (batch_id, summary_id))
    
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return rows_affected > 0

def get_all_summaries(sort_by="timestamp", sort_order="DESC", search_term="", batch_id=None):
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
    
    # Check if batch_id column exists
    cursor.execute("PRAGMA table_info(summaries)")
    columns = [col[1] for col in cursor.fetchall()]
    has_batch_id = "batch_id" in columns
    
    base_query = "SELECT * FROM summaries"
    conditions = []
    params = []
    
    # Add batch filter if specified and batch_id column exists
    if batch_id is not None and has_batch_id:
        conditions.append("batch_id = ?")
        params.append(batch_id)
    
    # Add search filter if specified
    if search_term:
        conditions.append("(filename LIKE ? OR summary LIKE ? OR tags LIKE ?)")
        search_pattern = f"%{search_term}%"
        params.extend([search_pattern, search_pattern, search_pattern])
    
    # Build final query
    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    
    query = f"{base_query} ORDER BY {sort_by} {sort_order}"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    summaries = []
    for row in rows:
        summary_data = {
            "id": row["id"],
            "filename": row["filename"],
            "timestamp": row["timestamp"],
            "text_length": row["text_length"],
            "summary": row["summary"],
            "tags": row["tags"] if "tags" in row.keys() else ""
        }
        
        # Add batch_id if it exists
        if has_batch_id:
            summary_data["batch_id"] = row["batch_id"] if row["batch_id"] is not None else 1
        else:
            summary_data["batch_id"] = 1
            
        summaries.append(summary_data)
    
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

def delete_all_summaries(batch_id=None):
    """Delete all summaries from the database, optionally filtered by batch."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if batch_id is not None:
        cursor.execute("DELETE FROM summaries WHERE batch_id = ?", (batch_id,))
    else:
        cursor.execute("DELETE FROM summaries")
    
    rows_affected = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    return rows_affected 