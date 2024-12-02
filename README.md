# SEC Form ADV Chatbot

## Overview
The **SEC Form ADV Chatbot** is a comprehensive, automated tool designed to interact with users and answer questions about financial advisory information contained in SEC Form ADV filings. Built with **Streamlit** for a web interface, the chatbot leverages **OpenAI’s language model** to interpret user questions, retrieve relevant data from a structured SQLite database, and generate contextually accurate answers.

SEC Page for File ADV (Includes Historical Data and Full Form): https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers

## Table of Contents
1. [Project Architecture](#project-architecture)
2. [Components](#components)
    - [Streamlit Interface](#streamlit-interface)
    - [PDF Text Extraction](#pdf-text-extraction)
    - [OpenAI Query Generation](#openai-query-generation)
    - [SQL Query Generation](#sql-query-generation)
    - [SQL Database](#sql-database)
    - [Answer Synthesis](#answer-synthesis)
3. [Setup and Installation](#setup-and-installation)
4. [Usage](#usage)
5. [How to Adapt the Chatbot for Different Forms](#how-to-adapt-the-chatbot-for-different-forms)
6. [Troubleshooting](#troubleshooting)

---

## Project Architecture
The system is structured in modular components that allow for **PDF text extraction**, **natural language processing (NLP)** question interpretation, **SQL query generation**, **database retrieval**, and **answer synthesis**. Below is a high-level overview of each component’s role within the system:

- **User Interface (UI)**: The interface built with Streamlit allows users to upload files, type questions, select sample questions, and view responses from the chatbot.
- **PDF to Text Converter**: Converts each page of an uploaded PDF document into text using OCR (Optical Character Recognition) via `pytesseract`.
- **OpenAI Question Processing**: Translates natural language questions into relevant SQL column searches.
- **SQL Query Generator**: Using database column mappings and sample data snapshots, the system constructs a SQL query based on OpenAI’s interpretation of the question.
- **Database Interaction**: Connects to a SQLite database containing structured data from the Form ADV, which is created from an uploaded Excel file.
- **Answer Synthesis**: OpenAI GPT-4-o generates natural language answers based on SQL query results to provide user-friendly responses.

<img width="1040" alt="Screenshot 2024-12-02 at 1 17 21 PM" src="https://github.com/user-attachments/assets/7a1782f5-53d2-42c7-a512-49066056a43e">


---

## Components

### Streamlit Interface
The **Streamlit UI** facilitates user interactions with the chatbot. Users can upload an Excel database, load text from a PDF, and type or select sample questions. The interface guides the flow through each phase:
1. **Load Database**: Upload and convert Excel data to a SQLite database.
2. **Text Extraction from PDF**: Processes and displays text from an uploaded PDF (e.g., Form ADV).
3. **Question Input and Answer Generation**: Enables users to ask questions about the document and view the chatbot’s responses.

### PDF Text Extraction
The function `extract_text_from_pdf(pdf_path)` uses `pytesseract` to process each page of the PDF document and converts it to a readable text format. This text serves as input for the question interpretation step.

### OpenAI Query Generation
Using OpenAI’s API, the system processes the document text along with user questions to identify relevant columns or sections within Form ADV. Two key functions:
- **Query Generation (Part 1)**: Determines the columns or document sections related to the question.
- **SQL Query Mapping (Part 2)**: Translates the column information from Part 1 into a SQL query for database retrieval.

### SQL Query Generation
The function `generate_sql_query` receives the interpreted document items and mappings from OpenAI, using them to construct an appropriate SQL query. It includes SQL operations such as `SUM`, `AVG`, or `COUNT` depending on the user’s question.

### SQL Database
The **SQLite database**, generated from an uploaded Excel file, stores structured data for Form ADV. It allows efficient querying and retrieval of specific financial or business information. Relevant columns are identified based on question intent and matched with OpenAI’s guidance.

### Answer Synthesis
The chatbot uses OpenAI’s language model to format the SQL query output into a readable, natural-language response. The response provides detailed answers in the context of the original question.

---

## Setup and Installation

### Prerequisites
- **Python 3.8** or later
- Packages: `streamlit`, `openai`, `pandas`, `sqlite3`, `pytesseract`, `pdf2image`, `python-dotenv`
- **Tesseract OCR** (required for `pytesseract`)

### Installation
1. **Clone the Repository**:
   ```bash
   git clone <repository_url>
   cd <repository_name>
2. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
4. **Make sure Tesseract OCR is installed in your system, as it is an external dependency.**
   ```bash
   sudo apt install tesseract-ocr #Ubuntu
   brew install tesseract #Mac
5. **Set up your environment variables:** Create a .env file in the project directory with your OpenAI API key:
   ```bash
   OAI=<your_openai_api_key>
6. **Run the Streamlit App**
   ```bash
   streamlit run sec_app.py

## Usage

1. **Upload Your Data**: Upload an Excel file to generate the SQLite database for Form ADV.
2. **Extract PDF Text**: Process and display text from an uploaded PDF (e.g., Form ADV).
3. **Ask a Question**: Use the text box or select a sample question. The app will:
   - Identify relevant sections of Form ADV.
   - Generate a SQL query to retrieve data.
   - Return a natural-language answer based on the data.

---

## How to Adapt the Chatbot for Different Forms

To create a chatbot for forms other than Form ADV, such as other financial or regulatory documents, follow these steps:

1. **Replace Document-Specific Instructions**:
   - Update the document instructions in the `query_openai_part1()` function to reflect the structure of the new form.
   - For instance, if the new form has different item numbers or sections, modify the instructions to guide the chatbot in selecting relevant items.

2. **Modify SQL Query Generation Logic**:
   - Update mappings between document sections and database columns in `generate_sql_query()`.
   - Ensure that the SQL query generator function reflects the specific column names and logic relevant to the new document.

3. **Adjust Sample Questions**:
   - Update or add relevant sample questions for the new document type, ensuring they align with the structure and data contained in the document.
   - **Example**: If the new form includes sections on compliance, add sample questions like "What are the compliance requirements?"

4. **Test and Refine**:
   - After modifying the code, test the chatbot with the new document to ensure it accurately interprets questions, queries the database, and provides correct answers.
   - Refine mappings or instructions as needed based on testing feedback.

---

## Troubleshooting

- **Connection Issues with OpenAI API**: Check that your API key is correctly loaded from the `.env` file and that the API is accessible.
- **OCR Accuracy**: If the extracted text from PDFs is inaccurate, consider adjusting `pytesseract` settings or using higher-resolution scans of the documents.
- **Database Connection Errors**: Ensure that the SQLite database is properly set up and that the paths to files are correctly specified.

