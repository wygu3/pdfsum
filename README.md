# PDF Summarizer

A Python application that allows you to upload multiple PDF files (up to 100) and summarize them using OpenAI's API. Each summary is saved to a local SQLite database and can be exported as a text file.

## Features

- Upload up to 100 PDF files
- Summarize PDFs using OpenAI's GPT API
- Save summaries with timestamps to a persistent SQLite database
- Search for summaries by filename, content, or tags
- Sort summaries by date, filename, PDF size, or ID
- Tag summaries for better organization
- Export individual summaries as text files
- Export all summaries as a single text file
- Delete individual summaries or clear all summaries
- Clean and intuitive UI built with Streamlit

## Requirements

- Python 3.7+
- Streamlit
- PyPDF2
- OpenAI API key
- SQLite (included in Python standard library)

## Installation

1. Clone this repository or download the files

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Set up your OpenAI API key:
   - Option 1: Enter it directly in the app
   - Option 2: Create a `.env` file with:
     ```
     OPENAI_API_KEY=your_api_key_here
     ```

## Usage

1. Run the app:
   ```
   streamlit run app.py
   ```

2. Open your web browser to the provided URL (typically http://localhost:8501)

3. Enter your OpenAI API key if you haven't set it up using a `.env` file

4. Upload one or more PDF files using the file uploader

5. Click "Summarize PDFs" to process the files

6. View the summaries and download them as text files

7. Manage your summaries:
   - Search for specific summaries using the search box
   - Sort summaries by date, filename, size, or ID
   - Add tags to categorize your summaries
   - Download individual summaries
   - Delete individual summaries
   - Export all summaries as a single text file
   - Clear all summaries from the database

## File Management Features

- **Sorting**: Change how summaries are ordered using the "Sort by" dropdown
- **Searching**: Find specific summaries by typing in the search box
- **Tagging**: Add comma-separated tags to each summary for organization
- **Filtering**: Use the search to filter by tags or content

## Database

The app uses a SQLite database (`summaries.db`) to persistently store your summaries. The database file is created in the same directory as the app.

## Notes

- The app uses OpenAI's GPT-3.5-turbo model for summarization
- Large PDFs are truncated to fit within token limits
- For very large PDFs, processing might take some time
- Summaries are stored in a local SQLite database for persistence between sessions

## License

MIT 