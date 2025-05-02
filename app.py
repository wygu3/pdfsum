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
import fitz  # PyMuPDF
import io
from PIL import Image
import tempfile
import uuid

# Check for .env file and load if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    st.warning("python-dotenv not installed. Using environment variables directly.")

# Get API key from environment variable or Streamlit secrets
api_key = None
# Check Streamlit secrets first
if hasattr(st, "secrets") and "openai" in st.secrets:
    api_key = st.secrets["openai"]["api_key"]
else:
    # Fall back to environment variable
    api_key = os.getenv("OPENAI_API_KEY")

# Define summary style presets
SUMMARY_PRESETS = {
    "concise": {
        "name": "Concise",
        "description": "A brief summary with core points only",
        "format": "paragraph",
        "length": "short",
        "max_tokens": 300,
        "system_prompt": "Create a concise summary focusing only on the most essential points."
    },
    "comprehensive": {
        "name": "Comprehensive",
        "description": "A detailed summary covering all main points",
        "format": "paragraph",
        "length": "medium",
        "max_tokens": 600,
        "system_prompt": "Create a comprehensive summary that covers all the main points in the document."
    },
    "executive": {
        "name": "Executive Summary",
        "description": "Business-focused with context and implications",
        "format": "paragraph",
        "length": "medium",
        "max_tokens": 500,
        "system_prompt": "Create an executive summary focusing on key business implications and strategic insights."
    },
    "bullet_points": {
        "name": "Bullet Points",
        "description": "Key takeaways in bullet point format",
        "format": "bullets",
        "length": "medium",
        "max_tokens": 500,
        "system_prompt": "Create a summary with key points in bullet point format."
    },
    "academic": {
        "name": "Academic",
        "description": "Formal analysis with citations if available",
        "format": "structured",
        "length": "long",
        "max_tokens": 800,
        "system_prompt": "Create a formal academic summary with analysis of methodology and findings."
    }
}

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
if 'include_visual_analysis' not in st.session_state:
    st.session_state.include_visual_analysis = False
if 'custom_instructions' not in st.session_state:
    st.session_state.custom_instructions = "Add any specific extraction preferences or formatting requirements here."
if 'current_batch_id' not in st.session_state:
    st.session_state.current_batch_id = 1
if 'show_create_batch' not in st.session_state:
    st.session_state.show_create_batch = False
if 'show_edit_batch' not in st.session_state:
    st.session_state.show_edit_batch = False
if 'batch_to_edit' not in st.session_state:
    st.session_state.batch_to_edit = None
if 'show_move_summary' not in st.session_state:
    st.session_state.show_move_summary = False
if 'summary_to_move' not in st.session_state:
    st.session_state.summary_to_move = None

# Function to extract text from PDF
def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        text += pdf_reader.pages[page_num].extract_text()
    return text

# Function to extract images from PDF
def extract_images_from_pdf(pdf_file, max_images=5):
    # Save the uploaded file to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
        temp_file.write(pdf_file.read())
        temp_path = temp_file.name
    
    # Reset file pointer for later use
    pdf_file.seek(0)
    
    # Open the PDF with PyMuPDF
    doc = fitz.open(temp_path)
    images = []
    
    # Limit number of images to prevent token overflow
    page_count = min(len(doc), max_images)
    
    for page_num in range(page_count):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
        
        img_data = io.BytesIO(pix.tobytes("png"))
        img = Image.open(img_data)
        
        # Create a unique filename
        img_filename = f"temp_img_{uuid.uuid4()}.png"
        img_path = os.path.join(tempfile.gettempdir(), img_filename)
        img.save(img_path)
        
        images.append({
            "path": img_path,
            "page": page_num + 1
        })
    
    # Close the document
    doc.close()
    
    # Clean up the temporary file
    os.unlink(temp_path)
    
    return images

# Function to convert image to base64 for OpenAI API
def image_to_base64(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')

# Function to get system prompt based on style and format
def get_system_prompt(style, custom_format=None, custom_length=None):
    preset = SUMMARY_PRESETS.get(style, SUMMARY_PRESETS["comprehensive"])
    
    # Start with the preset system prompt
    prompt = preset["system_prompt"]
    
    # If custom format is specified, add formatting instructions
    if custom_format == "paragraph":
        prompt += " Format as coherent paragraphs."
    elif custom_format == "bullets":
        prompt += " Format as a series of bullet points for each key insight."
    elif custom_format == "outline":
        prompt += " Format as a hierarchical outline with main points and sub-points."
    
    # If custom length is specified, add length instructions
    if custom_length == "short":
        prompt += " Keep it very concise, focusing only on the most critical information."
    elif custom_length == "medium":
        prompt += " Provide a balanced summary with key details and context."
    elif custom_length == "long":
        prompt += " Create a comprehensive summary with detailed explanations and context."
    
    return prompt

# Function to get max tokens based on style and length
def get_max_tokens(style, custom_length=None):
    preset = SUMMARY_PRESETS.get(style, SUMMARY_PRESETS["comprehensive"])
    base_tokens = preset["max_tokens"]
    
    # Adjust based on custom length if specified
    if custom_length == "short":
        return min(300, base_tokens)
    elif custom_length == "medium":
        return base_tokens
    elif custom_length == "long":
        return max(800, base_tokens)
    
    return base_tokens

# Function to summarize text using OpenAI API
def summarize_text(text, api_key, images=None, include_visual=False, custom_instructions=None):
    if not api_key:
        return "Error: API key not provided"
    
    try:
        # Import specific OpenAI client version
        from openai import OpenAI
        
        # Create client with minimal parameters
        client = OpenAI(api_key=api_key)
        
        # Truncate text if it's too long
        max_chars = 15000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        
        # Meta-prompt to be used for all API calls
        meta_prompt = """You are an expert information extractor tasked with analyzing the provided PDF document. Your goal is to meticulously extract all substantive information, key data points, concepts, arguments, conclusions, and factual statements presented within the document, mirroring the comprehensive understanding a human analyst would achieve after a careful reading. For documents with visuals, integrate visual information naturally into the summary rather than separately describing images. Use the visual elements to enhance understanding of concepts, data, and context

Instructions:

Comprehensive Content Extraction: Identify and capture the core message, main topics, supporting details, definitions, numerical data, findings, recommendations, and any other significant pieces of information.
Focus on Information, Not Structure: Extract what is being communicated (the content and meaning). Do not describe the document's layout, formatting, or structure (e.g., do not mention headings, paragraphs, lists, page numbers, font styles, or explicitly state 'this is a table'). However, do extract the information contained within these structures (e.g., extract the data from a table, but don't say 'the following data is from a table').
Synthesize and Avoid Redundancy: Present the extracted information concisely. If the same point or piece of data is mentioned multiple times in different ways or sections, capture the information only once in your output. Synthesize related points where appropriate to provide a clear and non-repetitive summary of the document's content.
Accuracy and Completeness: Ensure the extracted information accurately reflects the source document. Strive for completeness regarding all unique, substantive points made in the PDF.
Output Format: Present the extracted information in a clear, logical, and easily digestible format (e.g., bullet points, numbered lists, or concise paragraphs grouped by topic, as appropriate for the content)."""
        
        # Combine meta-prompt with any custom instructions
        if custom_instructions and custom_instructions.strip():
            system_prompt = f"{meta_prompt}\n\nAdditional instructions: {custom_instructions}"
        else:
            system_prompt = meta_prompt
        
        # Default max tokens
        max_tokens = 600
        
        # If visual analysis is enabled and images are provided
        if include_visual and images and len(images) > 0:
            try:
                # Use GPT-4o model with vision capabilities
                messages = [
                    {"role": "system", "content": system_prompt}
                ]
                
                # Add text content
                messages.append({
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": f"Please analyze this document, treating visual elements as an integral part of the content. The text content is:\n\n{text}"}
                    ]
                })
                
                # Add images content with page numbers
                for img in images:
                    img_base64 = image_to_base64(img["path"])
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Page {img['page']} visual:"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{img_base64}"
                                }
                            }
                        ]
                    })
                
                # Final instruction
                messages.append({
                    "role": "user",
                    "content": "Now, provide your comprehensive analysis that naturally integrates insights from both the text and visuals."
                })
                
                # Call the API with vision capabilities
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    max_tokens=max_tokens
                )
                
                # Clean up temporary image files
                for img in images:
                    try:
                        os.remove(img["path"])
                    except:
                        pass
            except Exception as e:
                # Fall back to text-only summary if vision fails
                st.warning(f"Visual analysis failed: {str(e)}. Falling back to text-only summary.")
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Please analyze the following document:\n\n{text}"}
                    ],
                    max_tokens=max_tokens
                )
        else:
            # Standard text-only summary
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Please analyze the following document:\n\n{text}"}
                ],
                max_tokens=max_tokens
            )
        
        return response.choices[0].message.content
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        st.error(f"Full error: {error_details}")
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

# Function to toggle visual analysis
def toggle_visual_analysis():
    st.session_state.include_visual_analysis = not st.session_state.include_visual_analysis

# Function to update custom instructions
def update_custom_instructions(instructions):
    st.session_state.custom_instructions = instructions

# Function to update current batch
def set_current_batch(batch_id):
    st.session_state.current_batch_id = batch_id
    st.rerun()

# Function to toggle create batch form
def toggle_create_batch():
    st.session_state.show_create_batch = not st.session_state.show_create_batch

# Function to toggle edit batch form
def toggle_edit_batch(batch_id=None):
    st.session_state.show_edit_batch = not st.session_state.show_edit_batch
    st.session_state.batch_to_edit = batch_id

# Function to show move summary dialog
def show_move_summary_dialog(summary_id):
    st.session_state.show_move_summary = True
    st.session_state.summary_to_move = summary_id

# Function to hide move summary dialog
def hide_move_summary_dialog():
    st.session_state.show_move_summary = False
    st.session_state.summary_to_move = None

# App title and description
st.title("PDF Summarizer")
st.write("Upload up to 100 PDFs to summarize them using AI.")

# API key input
api_key_input = st.text_input("OpenAI API Key", value=st.session_state.api_key if st.session_state.api_key else "", 
                             type="password", help="Enter your OpenAI API key")
if api_key_input:
    st.session_state.api_key = api_key_input

# Create tabs for Upload and Manage
tab1, tab2 = st.tabs(["Upload & Summarize", "Manage Summaries"])

with tab1:
    # File uploader
    uploaded_files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)

    # Summary customization options
    st.subheader("Summary Options")
    col1, col2 = st.columns([3, 1])

    with col1:
        # Custom instructions text area
        custom_instructions = st.text_area(
            "Additional Instructions (Optional)", 
            value=st.session_state.custom_instructions,
            height=100,
            help="Add any additional preferences for information extraction. These will be combined with our core extraction algorithm.",
            placeholder="Example: Focus on financial data and exclude any marketing claims. Format the output as a numbered list."
        )
        if custom_instructions != st.session_state.custom_instructions:
            update_custom_instructions(custom_instructions)
            
        # Visual analysis toggle moved here, underneath the text box
        st.checkbox("Include visual analysis", 
                   value=st.session_state.include_visual_analysis,
                   help="When enabled, the AI will analyze images, charts, and visual layouts in the PDF. Requires more processing time and tokens.",
                   on_change=toggle_visual_analysis)

    with col2:
        # Batch selection for new summaries
        st.subheader("Batch Selection")
        batches = db.get_all_batches()
        batch_options = {batch["id"]: batch["name"] for batch in batches}
        selected_batch = st.selectbox(
            "Save to batch",
            options=list(batch_options.keys()),
            format_func=lambda x: batch_options[x],
            index=list(batch_options.keys()).index(st.session_state.current_batch_id) if st.session_state.current_batch_id in batch_options else 0
        )
        
        # Create new batch button
        if st.button("Create New Batch"):
            toggle_create_batch()
    
    # Create new batch form
    if st.session_state.show_create_batch:
        st.subheader("Create New Batch")
        with st.form("create_batch_form"):
            batch_name = st.text_input("Batch Name", placeholder="Enter a name for this batch")
            batch_description = st.text_area("Description (optional)", placeholder="Enter a description for this batch")
            
            submitted = st.form_submit_button("Create Batch")
            if submitted and batch_name:
                new_batch_id = db.create_batch(batch_name, batch_description)
                st.session_state.current_batch_id = new_batch_id
                st.session_state.show_create_batch = False
                st.success(f"Created new batch: {batch_name}")
                st.rerun()

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
                
                # If visual analysis is enabled, extract images from PDF
                images = None
                if st.session_state.include_visual_analysis:
                    uploaded_file.seek(0)  # Reset file pointer
                    status_text.text(f"Extracting images from {uploaded_file.name}...")
                    try:
                        images = extract_images_from_pdf(uploaded_file)
                    except Exception as e:
                        st.warning(f"Failed to extract images: {str(e)}. Continuing with text-only summarization.")
                        images = None
                
                # Summarize text (and images if enabled)
                status_text.text(f"Generating summary for {uploaded_file.name}...")
                summary = summarize_text(
                    text, 
                    st.session_state.api_key, 
                    images, 
                    st.session_state.include_visual_analysis,
                    st.session_state.custom_instructions
                )
                
                # Save summary to database
                db.save_summary_to_db(uploaded_file.name, len(text), summary, "", selected_batch)
                
                # Update progress
                progress_bar.progress((i + 1) / len(uploaded_files))
                
            status_text.text("All PDFs processed!")
            time.sleep(1)
            status_text.empty()
            progress_bar.empty()
            
            st.success(f"Successfully summarized {len(uploaded_files)} PDFs")
            st.rerun()

with tab2:
    # Batch management
    st.subheader("Batch Management")
    
    # Get all batches
    batches = db.get_all_batches()
    
    # Create columns for batch selection and actions
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # Batch selection
        batch_options = {batch["id"]: f"{batch['name']} ({batch['summary_count']} summaries)" for batch in batches}
        selected_batch = st.selectbox(
            "Select Batch",
            options=list(batch_options.keys()),
            format_func=lambda x: batch_options[x],
            index=list(batch_options.keys()).index(st.session_state.current_batch_id) if st.session_state.current_batch_id in batch_options else 0
        )
        
        if selected_batch != st.session_state.current_batch_id:
            set_current_batch(selected_batch)
    
    with col2:
        # Batch actions
        col2a, col2b = st.columns(2)
        with col2a:
            if st.button("New Batch"):
                toggle_create_batch()
        
        with col2b:
            if st.button("Edit Batch"):
                toggle_edit_batch(st.session_state.current_batch_id)
    
    # Create new batch form
    if st.session_state.show_create_batch:
        st.subheader("Create New Batch")
        with st.form("create_batch_form_2"):
            batch_name = st.text_input("Batch Name", placeholder="Enter a name for this batch", key="batch_name_2")
            batch_description = st.text_area("Description (optional)", placeholder="Enter a description for this batch", key="batch_desc_2")
            
            submitted = st.form_submit_button("Create Batch")
            if submitted and batch_name:
                new_batch_id = db.create_batch(batch_name, batch_description)
                st.session_state.current_batch_id = new_batch_id
                st.session_state.show_create_batch = False
                st.success(f"Created new batch: {batch_name}")
                st.rerun()
    
    # Edit batch form
    if st.session_state.show_edit_batch and st.session_state.batch_to_edit:
        # Get current batch details
        current_batch = next((b for b in batches if b["id"] == st.session_state.batch_to_edit), None)
        
        if current_batch:
            st.subheader(f"Edit Batch: {current_batch['name']}")
            with st.form("edit_batch_form"):
                batch_name = st.text_input("Batch Name", value=current_batch["name"])
                batch_description = st.text_area("Description", value=current_batch["description"] or "")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    submitted = st.form_submit_button("Save Changes")
                with col2:
                    delete_batch = st.form_submit_button("Delete Batch", type="secondary")
                with col3:
                    cancel = st.form_submit_button("Cancel")
                
                if submitted and batch_name:
                    db.update_batch(st.session_state.batch_to_edit, batch_name, batch_description)
                    st.session_state.show_edit_batch = False
                    st.success(f"Updated batch: {batch_name}")
                    st.rerun()
                
                if delete_batch:
                    # Prevent deleting last batch
                    if len(batches) > 1:
                        # Delete the batch
                        db.delete_batch(st.session_state.batch_to_edit)
                        # Set current batch to the first remaining batch
                        remaining_batches = [b for b in batches if b["id"] != st.session_state.batch_to_edit]
                        if remaining_batches:
                            st.session_state.current_batch_id = remaining_batches[0]["id"]
                        st.session_state.show_edit_batch = False
                        st.success(f"Deleted batch: {current_batch['name']}")
                        st.rerun()
                    else:
                        st.error("Cannot delete the only batch. Create another batch first.")
                
                if cancel:
                    st.session_state.show_edit_batch = False
                    st.rerun()
    
    # Show move summary dialog
    if st.session_state.show_move_summary and st.session_state.summary_to_move:
        st.subheader("Move Summary to Another Batch")
        
        # Get current summary details
        summaries = db.get_all_summaries(batch_id=st.session_state.current_batch_id)
        current_summary = next((s for s in summaries if s["id"] == st.session_state.summary_to_move), None)
        
        if current_summary:
            st.info(f"Moving summary: {current_summary['filename']}")
            
            # Batch selection (exclude current batch)
            target_batches = [b for b in batches if b["id"] != st.session_state.current_batch_id]
            
            if target_batches:
                target_batch_options = {batch["id"]: batch["name"] for batch in target_batches}
                target_batch = st.selectbox(
                    "Select target batch",
                    options=list(target_batch_options.keys()),
                    format_func=lambda x: target_batch_options[x]
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Move Summary"):
                        db.move_summary_to_batch(st.session_state.summary_to_move, target_batch)
                        hide_move_summary_dialog()
                        st.success(f"Moved summary to {target_batch_options[target_batch]}")
                        st.rerun()
                
                with col2:
                    if st.button("Cancel Move"):
                        hide_move_summary_dialog()
                        st.rerun()
            else:
                st.warning("No other batches available. Create a new batch first.")
                if st.button("Cancel"):
                    hide_move_summary_dialog()
                    st.rerun()
    
    # Display current batch description
    current_batch = next((b for b in batches if b["id"] == st.session_state.current_batch_id), None)
    if current_batch and current_batch["description"]:
        st.info(current_batch["description"])
    
    # Search and filter in current batch
    st.subheader(f"Summaries in {current_batch['name'] if current_batch else 'Current Batch'}")
    
    # Search and sort controls
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_term = st.text_input("Search summaries", value=st.session_state.search_term, key="search_in_batch")
        if search_term != st.session_state.search_term:
            update_search(search_term)

    with col2:
        sort_options = {"timestamp": "Date", "filename": "Filename", "text_length": "PDF Size", "id": "ID"}
        sort_by = st.selectbox("Sort by", options=list(sort_options.keys()), 
                              format_func=lambda x: sort_options[x],
                              index=list(sort_options.keys()).index(st.session_state.sort_by),
                              key="sort_by_in_batch")
        if sort_by != st.session_state.sort_by:
            set_sort(sort_by, st.session_state.sort_order)

    with col3:
        sort_order = st.selectbox("Order", options=["DESC", "ASC"], 
                                 format_func=lambda x: "Newest first" if x == "DESC" else "Oldest first",
                                 index=0 if st.session_state.sort_order == "DESC" else 1,
                                 key="sort_order_in_batch")
        if sort_order != st.session_state.sort_order:
            set_sort(st.session_state.sort_by, sort_order)
    
    # Get summaries from the current batch with sorting and filtering
    summaries = db.get_all_summaries(
        sort_by=st.session_state.sort_by,
        sort_order=st.session_state.sort_order,
        search_term=st.session_state.search_term,
        batch_id=st.session_state.current_batch_id
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
                col1, col2, col3, col4 = st.columns(4)
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
                    # Move to another batch button
                    if len(batches) > 1:  # Only show if there are other batches
                        if st.button("Move to Batch", key=f"move_{item['id']}"):
                            show_move_summary_dialog(item['id'])
                
                with col3:
                    # Delete button
                    if st.button("Delete Summary", key=f"delete_{item['id']}"):
                        show_delete_confirmation(item['id'])
        
        # Export all summaries in batch
        st.subheader("Batch Actions")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Export All Batch Summaries"):
                all_summaries = ""
                for item in summaries:
                    all_summaries += f"Filename: {item['filename']}\n"
                    all_summaries += f"ID: {item['id']}\n"
                    all_summaries += f"Timestamp: {item['timestamp']}\n"
                    if item['tags']:
                        all_summaries += f"Tags: {item['tags']}\n"
                    all_summaries += f"Summary:\n{item['summary']}\n\n"
                    all_summaries += "-" * 80 + "\n\n"
                
                # Add batch info to filename
                batch_name = current_batch['name'].replace(" ", "_") if current_batch else "batch"
                
                st.markdown(
                    get_text_download_link(
                        all_summaries, 
                        f"{batch_name}_summaries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", 
                        "Download All Batch Summaries"
                    ),
                    unsafe_allow_html=True
                )
        
        # Clear all summaries in batch
        with col2:
            with st.expander("Delete All Batch Summaries"):
                st.warning("This action cannot be undone!")
                if st.button("I understand, delete ALL summaries in this batch"):
                    rows_deleted = db.delete_all_summaries(batch_id=st.session_state.current_batch_id)
                    st.success(f"Successfully deleted {rows_deleted} summaries from this batch!")
                    st.rerun()
    else:
        st.info("No summaries found in this batch. Upload PDF files to get started.")

# Add some information in the sidebar
with st.sidebar:
    st.subheader("About")
    st.write("This app allows you to summarize PDFs using OpenAI's GPT API.")
    st.write("Upload one or more PDFs (up to 100) and get AI-generated summaries.")
    st.write("Each summary is saved to a local database and can be exported as a text file.")
    
    if st.session_state.include_visual_analysis:
        st.subheader("Visual Analysis Enabled")
        st.write("The app will analyze images and visual elements in your PDFs using GPT-4o.")
        st.write("This provides more comprehensive summaries with insights from both text and visuals.")
    
    st.subheader("Batch Management")
    st.write("Organize your summaries into batches for better management.")
    st.write("Each batch can contain multiple summaries and can be exported together.")
    
    st.subheader("Instructions")
    st.write("1. Enter your OpenAI API key")
    st.write("2. Upload PDF files (up to 100)")
    st.write("3. Write custom instructions for how you want the documents summarized")
    st.write("4. Select a batch or create a new one to store the summaries")
    st.write("5. Enable visual analysis if needed")
    st.write("6. Click 'Summarize PDFs'")
    st.write("7. Manage your summaries in the 'Manage Summaries' tab")
    
    st.subheader("Example Instructions")
    st.markdown("""
    - "Create bullet points of key takeaways"
    - "Provide a detailed academic summary with methodology analysis"
    - "Write a short executive summary focusing on business implications"
    - "Summarize in 3 paragraphs with a focus on the main arguments"
    - "Create a list of 5-7 important facts from the document"
    """)
    
    st.subheader("Stats")
    all_summaries = db.get_all_summaries()
    all_batches = db.get_all_batches()
    st.write(f"Total summaries: {len(all_summaries)}")
    st.write(f"Total batches: {len(all_batches)}")
    
    # Show database location
    st.subheader("Database")
    st.write(f"Summaries are stored in: {os.path.abspath(db.DB_FILE)}") 