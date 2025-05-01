import streamlit as st
import os
import PyPDF2
import requests
import json
import time
import openai
from datetime import datetime
import base64
import db

# Check for .env file and load if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    st.warning("python-dotenv not installed. Using environment variables directly.")

# Get API key from environment variable
api_key = os.getenv("OPENAI_API_KEY")

# Initialize session state variables if they don't exist
if 'api_key' not in st.session_state:
    st.session_state.api_key = api_key
if 'sort_by' not in st.session_state:
    st.session_state.sort_by = "timestamp"
if 'sort_order' not in st.session_state:
    st.session_state.sort_order = "DESC"
if 'search_term' not in st.session_state:
    st.session_state.search_term = ""
if 'show_delete_confirmation' not in st.session_state:
    st.session_state.show_delete_confirmation = False
if 'summary_to_delete' not in st.session_state:
    st.session_state.summary_to_delete = None

# Function to extract text from PDF
def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        text += pdf_reader.pages[page_num].extract_text()
    return text

# Function to summarize text using OpenAI API
def summarize_text(text, api_key):
    if not api_key:
        return "Error: API key not provided"
    
    client = openai.OpenAI(api_key=api_key)
    
    try:
        # Truncate text if it's too long (GPT-3.5-turbo has token limits)
        max_chars = 15000  # Approximation to stay within token limits
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes PDF documents."},
                {"role": "user", "content": f"Please summarize the following document:\n\n{text}"}
            ],
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error during API call: {str(e)}"

# Function to create a downloadable link for text
def get_text_download_link(text, filename, link_text):
    """Generate a link to download text as a file."""
    b64 = base64.b64encode(text.encode()).decode()
    href = f'<a href="data:file/txt;base64,{b64}" download="{filename}">{link_text}</a>'
    return href

# Initialize the database
db.init_db()

# Function to handle deletion confirmation
def show_delete_confirmation(summary_id):
    st.session_state.show_delete_confirmation = True
    st.session_state.summary_to_delete = summary_id

# Function to confirm deletion
def confirm_delete():
    if st.session_state.summary_to_delete:
        success = db.delete_summary(st.session_state.summary_to_delete)
        if success:
            st.session_state.show_delete_confirmation = False
            st.session_state.summary_to_delete = None
            st.success("Summary deleted successfully!")
            st.rerun()
        else:
            st.error("Failed to delete summary.")
    else:
        st.session_state.show_delete_confirmation = False

# Function to cancel deletion
def cancel_delete():
    st.session_state.show_delete_confirmation = False
    st.session_state.summary_to_delete = None

# Function to set sorting
def set_sort(sort_by, sort_order):
    st.session_state.sort_by = sort_by
    st.session_state.sort_order = sort_order
    st.rerun()

# Function to update search term
def update_search(term):
    st.session_state.search_term = term
    st.rerun()

# Function to update tags
def update_tags(summary_id, tags):
    db.update_summary_tags(summary_id, tags)
    st.success("Tags updated successfully!")
    st.rerun()

# App title and description
st.title("PDF Summarizer")
st.write("Upload up to 100 PDFs to summarize them using AI.")

# API key input
api_key_input = st.text_input("OpenAI API Key", value=st.session_state.api_key if st.session_state.api_key else "", 
                             type="password", help="Enter your OpenAI API key")
if api_key_input:
    st.session_state.api_key = api_key_input

# File uploader
uploaded_files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)

# Process files when submitted
if uploaded_files and st.button("Summarize PDFs"):
    if not st.session_state.api_key:
        st.error("Please enter your OpenAI API key")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Limit to 100 files
        if len(uploaded_files) > 100:
            st.warning("Maximum 100 files allowed. Processing only the first 100.")
            uploaded_files = uploaded_files[:100]
        
        for i, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Processing {uploaded_file.name} ({i+1}/{len(uploaded_files)})")
            
            # Extract text from PDF
            text = extract_text_from_pdf(uploaded_file)
            
            # Summarize text
            summary = summarize_text(text, st.session_state.api_key)
            
            # Save summary to database
            db.save_summary_to_db(uploaded_file.name, len(text), summary)
            
            # Update progress
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        status_text.text("All PDFs processed!")
        time.sleep(1)
        status_text.empty()
        progress_bar.empty()
        
        st.success(f"Successfully summarized {len(uploaded_files)} PDFs")
        st.rerun()

# Load and display summaries from database with sorting options
st.subheader("Manage Summaries")

# Search and sort controls
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    search_term = st.text_input("Search summaries", value=st.session_state.search_term)
    if search_term != st.session_state.search_term:
        update_search(search_term)

with col2:
    sort_options = {"timestamp": "Date", "filename": "Filename", "text_length": "PDF Size", "id": "ID"}
    sort_by = st.selectbox("Sort by", options=list(sort_options.keys()), 
                          format_func=lambda x: sort_options[x],
                          index=list(sort_options.keys()).index(st.session_state.sort_by))
    if sort_by != st.session_state.sort_by:
        set_sort(sort_by, st.session_state.sort_order)

with col3:
    sort_order = st.selectbox("Order", options=["DESC", "ASC"], 
                             format_func=lambda x: "Newest first" if x == "DESC" else "Oldest first",
                             index=0 if st.session_state.sort_order == "DESC" else 1)
    if sort_order != st.session_state.sort_order:
        set_sort(st.session_state.sort_by, sort_order)

# Get summaries with sorting and filtering
summaries = db.get_all_summaries(
    sort_by=st.session_state.sort_by,
    sort_order=st.session_state.sort_order,
    search_term=st.session_state.search_term
)

# Display delete confirmation dialog if needed
if st.session_state.show_delete_confirmation:
    with st.container():
        st.warning("Are you sure you want to delete this summary?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, delete it"):
                confirm_delete()
        with col2:
            if st.button("Cancel"):
                cancel_delete()

# Display summaries
if summaries:
    st.write(f"Found {len(summaries)} summaries")
    
    for item in summaries:
        with st.expander(f"{item['filename']} - {item['timestamp']} (ID: {item['id']})"):
            st.markdown(f"**Summary:**")
            st.write(item['summary'])
            
            # Tags
            tags = st.text_input("Tags (separate with commas)", 
                                value=item['tags'] if item['tags'] else "", 
                                key=f"tags_{item['id']}")
            
            if st.button("Update Tags", key=f"update_tags_{item['id']}"):
                update_tags(item['id'], tags)
            
            # Action buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                # Download button
                st.markdown(
                    get_text_download_link(
                        item['summary'], 
                        f"{item['filename'].replace('.pdf', '')}_summary.txt", 
                        "Download Summary"
                    ), 
                    unsafe_allow_html=True
                )
            
            with col2:
                # Delete button
                if st.button("Delete Summary", key=f"delete_{item['id']}"):
                    show_delete_confirmation(item['id'])
    
    # Export all summaries to a single text file
    st.subheader("Batch Actions")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Export All Summaries"):
            all_summaries = ""
            for item in summaries:
                all_summaries += f"Filename: {item['filename']}\n"
                all_summaries += f"ID: {item['id']}\n"
                all_summaries += f"Timestamp: {item['timestamp']}\n"
                if item['tags']:
                    all_summaries += f"Tags: {item['tags']}\n"
                all_summaries += f"Summary:\n{item['summary']}\n\n"
                all_summaries += "-" * 80 + "\n\n"
            
            st.markdown(
                get_text_download_link(
                    all_summaries, 
                    f"all_summaries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", 
                    "Download All Summaries"
                ),
                unsafe_allow_html=True
            )
    
    # Clear all summaries
    with col2:
        with st.expander("Delete All Summaries"):
            st.warning("This action cannot be undone!")
            if st.button("I understand, delete ALL summaries permanently"):
                rows_deleted = db.delete_all_summaries()
                st.success(f"Successfully deleted {rows_deleted} summaries!")
                st.rerun()
else:
    st.info("No summaries found. Upload PDF files to get started.")

# Add some information in the sidebar
with st.sidebar:
    st.subheader("About")
    st.write("This app allows you to summarize PDFs using OpenAI's GPT API.")
    st.write("Upload one or more PDFs (up to 100) and get AI-generated summaries.")
    st.write("Each summary is saved to a local database and can be exported as a text file.")
    
    st.subheader("Instructions")
    st.write("1. Enter your OpenAI API key")
    st.write("2. Upload PDF files (up to 100)")
    st.write("3. Click 'Summarize PDFs'")
    st.write("4. View and download the summaries")
    st.write("5. Sort, filter, and tag your summaries")
    
    st.subheader("Stats")
    all_summaries = db.get_all_summaries()
    st.write(f"Summaries in database: {len(all_summaries)}")
    
    # Show database location
    st.subheader("Database")
    st.write(f"Summaries are stored in: {os.path.abspath(db.DB_FILE)}") 