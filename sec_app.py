import streamlit as st
from openai import OpenAI
import pandas as pd
import sqlite3
import pytesseract
from pdf2image import convert_from_path
from dotenv import load_dotenv
import os

# Load environment variables and OpenAI client setup
load_dotenv()
api_key = os.getenv("OAI")
client = OpenAI(api_key=api_key)

# Load the Excel data into SQLite
@st.cache
def load_data():
    db_path = "RegisteredAdvisors.db"
    # Just confirm the database is accessible without reloading from Excel
    try:
        conn = sqlite3.connect(db_path)
        conn.close()
        return "Database connected successfully."
    except sqlite3.Error as e:
        return f"Failed to connect to the database: {e}"
# Upload and Convert Excel Data to SQLite Database 
@st.cache 
def convert_excel_to_sqlite(uploaded_file):
    # Load the Excel file into the pandas dataframe 
    df = pd.read_excel(uploaded_file)
    
    # Create SQLite database 
    conn = sqlite3.connect("UserUploadedData.db")
    df.to_sql("RegisteredAdvisors", conn, if_exists="replace", index=False)
    conn.close()
    return "Database created succesfully"



# Step 1: Extract text from each page in the PDF
@st.cache
def extract_text_from_pdf(pdf_path):
    images = convert_from_path(pdf_path)
    extracted_text = ""
    for page in images:
        text = pytesseract.image_to_string(page)
        extracted_text += text + "\n\n"
    return extracted_text

# Step 1: Query OpenAI model with extracted text for relevant columns
def query_openai_part1(text, question):
    part1_system_message = """
        You are an assistant trained to identify specific item numbers, question numbers, and sub-items from the Form ADV document to support SQL query generation. Your task is to locate the relevant columns with information necessary to answer user questions, which will later be manipulated with SQL in Part 2.

        Important Information:
        1. **Item 5.D - Type of Client Data**:
        - 5D(a)(1) to 5D(n)(1): Number of Clients for each client type, structured as follows:
            - 5D(a)(1): "Individuals (other than high net worth individuals)"
            - 5D(b)(1): "High net worth individuals"
            - 5D(c)(1): "Banking or thrift institutions"
            - (continues similarly through each client type up to)
            - 5D(n)(1): "Other"
        - Each client type (from a to n) also has:
            - 5D(a)(2) to 5D(n)(2): Column indicating if there are fewer than 5 clients for each type.
            - 5D(a)(3) to 5D(n)(3): Amount of Regulatory Assets under Management for each client type.


        2. **Item 9 - Custody of Client Assets**:
        - 9A(1)(a): Custody of "cash or bank accounts" by the firm itself.
        - 9A(1)(b): Custody of "securities" by the firm itself.
        - 9A(2)(a): Approximate amount of client funds in custody by the firm.
        - 9A(2)(b): Total number of clients for which the firm has custody of assets.
        - 9B(1)(a) to 9B(2)(b): Similar fields for custody by related persons.

        3. **Definition of "Small Registered Investment Advisors"**:
        - An advisor is considered "small" if they answered "No" to all the following items in Form ADV:
            - Item 12A
            - Item 12B(1)
            - Item 12B(2)
            - Item 12C(1)
            - Item 12C(2)
        - This is used as the small entity definition for identifying "small registered investment advisors" (RIAs).

        4. **Cell Values for Yes/No Answers**:
        - Responses are typically represented by "Y" for Yes and "N" for No in the columns. When identifying relevant columns based on a question, ensure that you check if the presence of a "Y" or "N" response affects whether the column should be included.
        - Example: If the question asks to find advisors that are "small," include columns 12A, 12B1, 12B2, 12C1, and 12C2, and indicate that an "N" in each column signifies a small advisor.


        **Instructions**:

        1. **Find Relevant Columns**: Your primary goal is to locate the columns containing data necessary to calculate the answer, even if the form does not contain an exact match for the question.
        - Example: If asked for the fraction of advisors with fewer than 2000 clients, identify columns that record client counts (Item 5.D (e.g., 5D(a)(1), 5D(b)(1), etc.)) as relevant data sources.

        2. **Interpreting Specific and Threshold-Based Questions**:
        - When a question includes thresholds or specific counts (e.g., "more than one million clients"), identify the columns with general client counts as relevant data.
        - If the question involves categories without precise values (e.g., "fraction of advisors with a certain trait"), include all relevant columns even if they do not provide an exact match for the threshold.

        3. **Provide Closest Match**: If an exact match isn’t available, give the closest item and sub-item numbers relevant to the question's context.

        4. **Be concise**: 
            - Provide the item numbers and sub-items that contain the most relevant data.
            - Avoid unnecessary information that does not directly help answer the question.
            
        **Examples**:
        - Question: "What is the total number of assets under management of the investment advisers, in trillion dollars?"
        - Answer: Item 5.D, specifically columns 5D(a)(3), 5D(b)(3), ..., etc. for all client types.

        - Question: "What is the number of advisers with each more than one million clients?"
        - Answer: Item 5.D, specifically columns 5D(a)(1), 5D(b)(1), ..., 5D(c)(1), etc.

        - Question: "What fraction of advisers provide portfolio management services to their clients?"
        - Answer: The relevant information is in 5.G.(2), 5.G.(3), 5.G.(4), and 5.G.(5).

        - Question: "What is the total assets under custody of advisers, in trillion dollars?"
        - Answer: Item 9.A(2)(a) for the firm's custody of client funds and Item 9.B(2)(a) for related persons' custody of client funds.

        Focus on providing item numbers and sub-items based on the closest information relevant to the question's requirements.

        """
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": part1_system_message},
            {"role": "user", "content": f"{question}\n\nDocument Text:\n{text}"}
        ]
    )
    return completion.choices[0].message.content

# Step 2: Generate SQL query based on Part 1 answer
def generate_sql_query(question, part1_answer):
    conn = sqlite3.connect("UserUploadedData.db")
    df = pd.read_sql_query("SELECT * FROM RegisteredAdvisors LIMIT 5", conn)
    conn.close()

    # Prepare column names with sample data
    column_samples = {}
    for column in df.columns:
        column_samples[column] = df[column].dropna().unique().tolist()[:5]

    # Format column samples as a string for context
    formatted_column_samples = "\n".join(
        f"{col}: {samples}" for col, samples in column_samples.items()
    )   

    part2_system_message = f"""
        You are a SQL assistant with knowledge of the column structure of a financial advisors database.
        Here is a list of column names and sample data from each column:
        {', '.join(map(str, formatted_column_samples))}

        Mapping Examples:
        - "Item 1.A" maps to "1A".
        - "Item 5.B.(1)" maps to "5B(1)".
        - "Item 6, Part A" maps to ["6A(1)", "6A(2)", ... "6A(14)", "6A(14)-Other"].

        Instructions:
        1. Use the answer from Phase 1, which contains an item identifier, to identify the corresponding column(s) in the database.
            - If the identifier maps to a single column, use that column.
            - If it maps to a group of columns, include all columns in that group.
            - If the answer is broad, such as "Item 9.A.(1)," and there are sub-columns like "9A(1)(a)" and "9A(1)(b)," include all relevant sub-columns in the query to capture all parts of the subquestion.
            - Some questions may directly map to specific columns based on their context, even without an identifier. Use column names directly if they align with the question, such as "Total Gross Assets of Private Funds."
        2. Refer to the original question to determine the intent and any specific conditions for the SQL query:
            - If the question asks for an "average," use the AVG function.
            - If it requests a "total," use SUM.
            - If it asks for a count, use COUNT.
            - Use other SQL functions or aggregation as appropriate based on the context.
        3. Combine the columns identified from the answer in Phase 1 with the intent and conditions inferred from the original question.
        4. Structure the SQL output flexibly, based on the user's intent. Here are some example formats:
            - For direct selection: SELECT [columns] FROM RegisteredAdvisors WHERE [conditions if any].
            - For aggregation: SELECT AVG([column]) FROM RegisteredAdvisors WHERE [conditions if any] (if the question asks for averages).
            - Apply similar structures for SUM, COUNT, and any other relevant SQL functionality.
            - If the question is asking for a specific company, include a WHERE clause to filter by the company name. In the database, all company names are in all caps in the 'Primary Business Name' column.
        5. Use the sample data to identify the correct SQL function and conditions: apply SUM, AVG, or COUNT for numerical data, and use exact matches for categorical data like "Y" for yes and "N" for no in WHERE clauses.  
        6. Use the appropriate SQL format based on the type of information requested and return the generated SQL query.
        7. Sometimes, part 1 may return no information. In such cases, use the original question to identify the relevant columns directly from the database or 
            you may be able to create the SQL query without the need for specific columns. For example, if the question asks for the total number of registered advisors,
            you can directly return the SQL query `SELECT COUNT(*) FROM RegisteredAdvisors.db;`.

        Additional Information: 
        1. **Legal Name Formatting**: 
        - The legal name of a business is in all caps in the data. If the question is about a specific firm, 
        ensure that you use the legal name in all caps for accurate identification. 
        - Ex. If the question asks for the total assets under management of "ABC Financial Services," 
            you would use the legal name "ABC FINANCIAL SERVICES" in the where clause of the query.
            
        Example Scenarios:
        - Question: "What is the fraction of advisers having custody of clients' cash or securities?"
        - Part 1 Answer: Relevant columns are 9A(1)(a) and 9A(1)(b).
        - SQL Query: `SELECT COUNT(*) * 1.0 / (SELECT COUNT(*) FROM RegisteredAdvisors.db) AS fraction_having_custody FROM RegisteredAdvisors WHERE "9A(1)(a)" = 'Y' OR "9A(1)(b)" = 'Y';`

        - Question: "What is the total number of assets under management of the investment advisers, in trillion dollars?"
        - Part 1 Answer: Columns 5D(a)(3), 5D(b)(3), ..., to 5D(n)(3).
        - SQL Query: `SELECT SUM("5D(a)(3)" + "5D(b)(3)" + ... + 5D(n)(3)) / 1e12 AS total_assets_in_trillions FROM RegisteredAdvisors;`

        Respond with ONLY the full SQL query based on the information provided in Part 1 and the question's 
        intent. Don't include anything else in the response besides the exact SQL query so the entire answer
        can be directly passed to the SQL interpreter without any need for cleaning.
        """
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": part2_system_message},
            {"role": "user", "content": f"Original Question: {question}\n\nPart 1 Answer: {part1_answer}"}
        ]
    )
    return completion.choices[0].message.content

# Step 3: Execute the SQL query on SQLite database
def execute_sql_query(query):
    connection = sqlite3.connect("RegisteredAdvisors.db")
    cursor = connection.cursor()
    query = query.replace("```sql", "").replace("```", "").replace("`", "").replace("sql", "").strip()
    try:
        cursor.execute(query)
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        st.error(f"Error executing query: {e}")
        return None
    finally:
        connection.close()

# Final Answer Generation based on SQL result
def get_final_answer_from_llm(question, sql_result):
    prompt = f"""
    Here is a question asked by the user: "{question}"
    The result of the SQL query for this question is: {sql_result}
    
    Based on this result, provide a clear and detailed answer to the user, making sure to interpret the result in the context of the original question.
    """
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an assistant skilled at interpreting SQL query results."},
            {"role": "user", "content": prompt}
        ]
    )
    return completion.choices[0].message.content


# Streamlit Interface
st.title("SEC File ADV Chatbot")

# Part 1: Load Database and Document Text Extraction
st.header("Part 1: Load Database and Extract Text from PDF")
db_status = load_data()
st.success(db_status)

# Load the uploaded data and create the SQLite database
st.header("Upload your advisor data (.xlsx) file")
uploaded_file = st.file_uploader("Choose a file", type="xlsx")

if uploaded_file:
    db_status = convert_excel_to_sqlite(uploaded_file)
    st.success(db_status)


# Define PDF path
pdf_path = "FileADV.pdf"
#extracted_text = extract_text_from_pdf(pdf_path)

extracted_text = """
FORM ADV (Paper Version)

e UNIFORM APPLICATION FOR INVESTMENT ADVISER
REGISTRATION
AND
e REPORT BY EXEMPT REPORTING ADVISERS

PART 1A

WARNING: Complete this form truthfully. False statements or omissions may result in
denial of your application, revocation of your registration, or criminal
prosecution. You must keep this form updated by filing periodic
amendments. See Form ADV General Instruction 4.

Check the box that indicates what you would like to do (check all that apply):

SEC or State Registration:

C1 Submit an initial application to register as an investment adviser with the SEC.

C1 Submit an initial application to register as an investment adviser with one or more states.
O Submit an annual updating amendment to your registration for your fiscal year ended

O Submit an other-than-annual amendment to your registration.

SEC or State Report by Exempt Reporting Advisers:

O Submit an initial report to the SEC.

C1 Submit a report to one or more state securities authorities.

O Submit an annual updating amendment to your report for your fiscal year ended
C1) Submit an other-than-annual amendment to your report.

C1 Submit a final report.

Item 1 Identifying Information

Responses to this Item tell us who you are, where you are doing business, and how we can
contact you. If you are filing an umbrella registration, the information in Item | should be
provided for the filing adviser only. General Instruction 5 provides information to assist you
with filing an umbrella registration.

A. Your full legal name (if you are a sole proprietor, your last, first, and middle names):

B. (1) Name under which you primarily conduct your advisory business, if different from
Ttem 1.A.

SEC 1707 (08-22) File 2 of 5


List on Section 1.B. of Schedule D any additional names under which you conduct your
advisory business.

(2) If you are using this Form ADV to register more than one investment adviser under
an umbrella registration, check this box 1.

If you check this box, complete a Schedule R for each relying adviser.
. Ifthis filing is reporting a change in your legal name (Item 1.A.) or primary business

name (Item 1.B.(1)), enter the new name and specify whether the name change is of 0
your legal name or O your primary business name:

. (1) If you are registered with the SEC as an investment adviser, your SEC file number:
801-

(2) If you report to the SEC as an exempt reporting adviser, your SEC file number:
802-

(3) If you have one or more Central Index Key numbers assigned by the SEC (“CIK
Numbers”), all of your CIK numbers:

. (1) If you have a number (“CRD Number”) assigned by the FINRA ’s CRD system or by
the IARD system, your CRD number:

(2) If you have additional CRD Numbers, your additional CRD numbers:

If your firm does not have a CRD number, skip this Item 1.E. Do not provide the CRD
number of one of your officers, employees, or affiliates.

. Principal Office and Place of Business

(1) Address (do not use a P.O. Box):

(number and street)

(city) (state/country) (zip +4/postal code)
If this address is a private residence, check this box: O
List on Section 1.F. of Schedule D any office, other than your principal office and place

of business, at which you conduct investment advisory business. If you are applying for
registration, or are registered, with one or more state securities authorities, you must list


all of your offices in the state or states to which you are applying for registration or with
whom you are registered. If you are applying for SEC registration, if you are registered
only with the SEC, or if you are reporting to the SEC as an exempt reporting adviser, list
the largest twenty-five offices in terms of numbers of employees as of the end of your
most recently completed fiscal year.

(2) Days of week that you normally conduct business at your principal office and place
of business:

O Monday - Friday O Other:

Normal business hours at this location:

(3) Telephone number at this location:

(areacode) (telephone number)

(4) Facsimile number at this location, if any:

(areacode) (facsimile number)
(5) What is the total number of offices, other than your principal office and place of
business, at which you conduct investment advisory business as of the end of your

most recently completed fiscal year?

. Mailing address, if different from your principal office and place of business address:

(number and street)

(city) (state/country) (zip+4/postal code)
If this address is a private residence, check this box: Oo

. If you are a sole proprietor, state your full residence address, if different from your
principal office and place of business address in Item 1.F.:

(number and street)

(city) (state/country) (zip+4/postal code)

Do you have one or more websites or accounts on publicly available social media
platforms (including, but not limited to, Twitter, Facebook and LinkedIn)?


Yes Of No O

If “ves,” list all firm website addresses and the address for each of the firm’s accounts on
publicly available social media platforms on Section 1.1. of Schedule D. If a website
address serves as a portal through which to access other information you have published
on the web, you may list the portal without listing addresses for all of the other
information. You may need to list more than one portal address. Do not provide the
addresses of websites or accounts on publicly available social media platforms where
you do not control the content. Do not provide the individual electronic mail (e-mail)
addresses of employees or the addresses of employee accounts on publicly available
social media platforms.

J. Chief Compliance Officer
(1) Provide the name and contact information of your Chief Compliance Officer. If you

are an exempt reporting adviser, you must provide the contact information for your
Chief Compliance Officer, if you have one. If not, you must complete Item 1.K.

below.
(name)
(other titles, if any)
(area code) (telephone number) (area code) (facsimile number, if any)
(number and street)
(city) (state/country) (zip+4/postal code)

(electronic mail (e-mail) address, if Chief Compliance Officer has one)

(2) If your Chief Compliance Officer is compensated or employed by any person other
than you, a related person or an investment company registered under the Investment
Company Act of 1940 that you advise for providing chief compliance officer
services to you, provide the person’s name and IRS Employer Identification Number

(if any):



K. Additional Regulatory Contact Person: Ifa person other than the Chief Compliance
Officer is authorized to receive information and respond to questions about this Form
ADV, you may provide that information here.

(name)

(titles)

(area code) (telephone number) (area code) (facsimile number, if any)

(number and street)

(city) (state/country) (zip+4/postal code)

(electronic mail (e-mail) address, if contact person has one)

L. Do you maintain some or all of the books and records you are required to keep under
Section 204 of the Advisers Act, or similar state law, somewhere other than your
principal office and place of business?

Yess O No O
If “yes,” complete Section 1.L. of Schedule D.

M. Are you registered with a foreign financial regulatory authority? Yes O No O
Answer “no” if you are not registered with a foreign financial regulatory authority, even
if you have an affiliate that is registered with a foreign financial regulatory authority. If

“yes,” complete Section 1.M. of Schedule D.

N. Are you a public reporting company under Sections 12 or 15(d) of the Securities
Exchange Act of 1934?

Yes O No O

O. Did you have $1 billion or more in assets on the last day of your most recent fiscal year?

Yes O No Oo

If yes, what is the approximate amount of your assets:


$1 billion to less than $10 billion Oo

$10 billion to less than $50 billion O

$50 billion or more O
For purposes of Item 1.O. only, “assets” refers to your total assets, rather than the
assets you manage on behalf of clients. Determine your total assets using the total assets

shown on the balance sheet for your most recent fiscal year end.

P. Provide your Legal Entity Identifier if you have one:

A legal entity identifier is a unique number that companies use to identify each other in
the financial marketplace. You may not have a legal entity identifier.

Item 2
SEC Registration

Responses to this Item help us (and you) determine whether you are eligible to register with the
SEC. Complete this Item 2.A. only if you are applying for SEC registration or submitting an
annual updating amendment to your SEC registration. If you are filing an umbrella registration,
the information in Item 2 should be provided for the filing adviser only.

A. To register (or remain registered) with the SEC, you must check at least one of the Items
2.A.(1) through 2.A.(12), below. If you are submitting an annual updating amendment to
your SEC registration and you are no longer eligible to register with the SEC, check Item
2.A.(13). Part 1A Instruction 2 provides information to help you determine whether you
may affirmatively respond to each of these items.

You (the adviser):
O (1) area large advisory firm that either:

(a) has regulatory assets under management of $100 million (in U.S. dollars)
or more; or

(b) has regulatory assets under management of $90 million (in U.S. dollars) or
more at the time of filing its most recent annual updating amendment and is
registered with the SEC;

O (2) area mid-sized advisory firm that has regulatory assets under management of
$25 million (in U.S. dollars) or more but less than $100 million (in U.S. dollars)
and you are either:


O (3)

O @)

(a) not required to be registered as an adviser with the state securities authority
of the state where you maintain your principal office and place of business;
or

(b) not subject to examination by the state securities authority of the state
where you maintain your principal office and place of business;

Click HERE for a list of states in which an investment adviser, if registered,
would not be subject to examination by the state securities authority.

Reserved;

have your principal office and place of business outside the United States;

(5) are an iivestment adviser (or subadviser) to an investment company

O (6)

O (7)

O (8)

O (9)

registered under the Investment Company Act of 1940;

are an investment adviser to a company which has elected to be a business
development company pursuant to section 54 of the Investment Company Act
of 1940 and has not withdrawn the election, and you have at least $25 million of
regulatory assets under management;

are a pension consultant with respect to assets of plans having an aggregate
value of at least $200,000,000 that qualifies for the exemption in rule
203A-2(a);

are a related adviser under rule 203A-2(b) that controls, is controlled by, or is
under common control with, an investment adviser that is registered with the
SEC, and your principal office and place of business is the same as the
registered adviser;

If you check this box, complete Section 2.A.(8) of Schedule D.

are an adviser relying on rule 203A-2(c) because you expect to be eligible for
SEC registration within 120 days;

If you check this box, complete Section 2.A.(9) of Schedule D.

O (10) are a multi-state adviser that is required to register in 15 or more states and is

relying on rule 203A-2(d);

If you check this box, complete Section 2.A.(10) of Schedule D.

O (11) are an Internet adviser relying on rule 203A-2(e);


SEC Reporting by Exempt Reporting Advisers

O (12) have received an SEC order exempting you from the prohibition against
registration with the SEC;

If you check this box, complete Section 2.A.(12) of Schedule D.

O (13) are no longer eligible to remain registered with the SEC.

B. Complete this Item 2.B. only if you are reporting to the SEC as an exempt reporting
adviser. Check all that apply. You:

O (1) qualify for the exemption from registration as an adviser solely to one or more
venture capital funds, as defined in rule 203(1)-1;

O (2) qualify for the exemption from registration because you act solely as an adviser
to private funds and have assets under management, as defined in rule

203(m)-1, in the United States of less than $150 million;

O (3) act solely as an adviser to private funds but you are no longer eligible to check

box 2.B.(2) because you have assets under management, as defined in rule

203(m)-1, in the United States of $150 million or more.

If you check box (2) or (3), complete Section 2.B. of Schedule D.

State Securities Authority Notice Filings and State Reporting by Exempt Reporting
Advisers

Cc.

Under state laws, SEC-registered advisers may be required to provide to state securities
authorities a copy of the Form ADV and any amendments they file with the SEC. These
are called notice filings. In addition, exempt reporting advisers may be required to
provide state securities authorities with a copy of reports and any amendments they file
with the SEC. If this is an initial application or report, check the box(es) next to the
state(s) that you would like to receive notice of this and all subsequent filings or reports
you submit to the SEC. If this is an amendment to direct your notice filings or reports to
additional state(s), check the box(es) next to the state(s) that you would like to receive

notice of this and all subsequent filings or reports you submit to the SEC. If tl
amendment to your registration to stop your notice filings or reports from goi
state(s) that currently receive them, uncheck the box(es) next to those state(s).

O AL O CT O HI KY MN 0 NH OH O SC
O AK O DE OQ ID LA MS 0 NJ OK O SD
O AZ O DC OL ME MO (] NM OR TN
O AR OF FL QIN MD MT OO NY PA OO) TX
O CA 0 GA OIA MA NE O) NC PR ©) UT
O wy 0 CO GU KS MI O) NV ND CO RI

his is an
ng to

VI
VA
WA
WV
Wi
VT



Ifyou are amending your registration to stop your notice filings or reports from going to
a state that currently receives them and you do not want to pay that state’s notice filing
or report filing fee for the coming year, your amendment must be filed before the end of
the year (December 31).

Item3 Form of Organization

If you are filing an umbrella registration, the information in Item 3 should be provided for the
filing adviser only.

A. How are you organized?

O Corporation O Sole Proprietorship O Limited Liability Partnership (LLP)
O Partnership (© Limited Liability Company (LLC) 11 Limited Partnership (LP)
O Other (specify):

If you are changing your response to this Item, see Part 1A Instruction 4.

B. In what month does your fiscal year end each year?

C. Under the laws of what state or country are you organized?

If you are a partnership, provide the name of the state or country under whose laws
your partnership was formed. If you are a sole proprietor, provide the name of the state
or country where you reside.
If you are changing your response to this Item, see Part 1A Instruction 4.
Item4 Successions

A. Are you, at the time of this filing, succeeding to the business of a registered investment
adviser, including, for example, a change of your structure or legal status (e.g., form of
organization or state of incorporation)?
O Yes O No
If “yes,” complete Item 4.B. and Section 4 of Schedule D.

B. Date of Succession:

(mm/dd/yyyy)

If you have already reported this succession on a previous Form ADV filing, do not
report the succession again. Instead, check “No.” See Part 1A Instruction 4.

Item5 Information About Your Advisory Business

9


Responses to this Item help us understand your business, assist us in preparing for on-site
examinations, and provide us with data we use when making regulatory policy. Part 1A

Instruction 5.a. provides additional guidance to newly formed advisers for completing this Item
5.

Employees

If you are organized as a sole proprietorship, include yourself as an employee in your
responses to Item 5.A. and Items 5.B.(1), (2), (3), (4), and (5). If an employee performs more
than one function, you should count that employee in each of your responses to Items 5.B.(1),

(2), (3), (4) and (5).

A. Approximately how many employees do you have? Include full- and part-time employees
but do not include any clerical workers.

B. (1) Approximately how many of the employees reported in 5.A. perform investment
advisory functions (including research)?

(2) Approximately how many of the employees reported in 5.A. are registered
representatives of a broker-dealer?

(3) Approximately how many of the employees reported in 5.A. are registered with one
or more state securities authorities as investment adviser representatives?

(4) Approximately how many of the employees reported in 5.A. are registered with one
or more state securities authorities as investment adviser representatives for an
investment adviser other than you?

(5) Approximately how many of the employees reported in 5.A. are licensed agents of an
insurance company or agency?

(6) Approximately how many firms or other persons solicit advisory clients on your
behalf?

In your response to Item 5.B.(6), do not count any of your employees and count a firm
only once - do not count each of the firm’s employees that solicit on your behalf.

10


Clients

In your responses to Items 5.C. and 5.D. do not include as “clients” the investors in a private
fund you advise, unless you have a separate advisory relationship with those investors.

C. (1) To approximately how many clients for whom you do not have regulatory assets
under management did you provide investment advisory services during your most
recently completed fiscal year?

(2) Approximately what percentage of your clients are non-United States persons?
%

D. For purposes of this Item 5.D., the category “individuals” includes trusts, estates, and
401(k) plans and IRAs of individuals and their family members, but does not include
businesses organized as sole proprietorships.

The category “business development companies” consists of companies that have made
an election pursuant to section 54 of the Investment Company Act of 1940. Unless you
provide advisory services pursuant to an investment advisory contract to an investment
company registered under the Investment Company Act of 1940, do not answer (d)(1) or
(d)(3) below.

Indicate the approximate number of your clients and amount of your total regulatory
assets under management (reported in Item 5.F. below) attributable to each of the
following type of client. If you have fewer than 5 clients in a particular category (other
than (d), (e), and (f)) you may check Item 5.D.(2) rather than respond to Item 5.D.(1).

The aggregate amount of regulatory assets under management reported in Item 5.D.(3)
should equal the total amount of regulatory assets under management reported in Item
5.F.(2)(c) below.

If a client fits into more than one category, select one category that most accurately
represents the client to avoid double counting clients and assets. If you advise a
registered investment company, business development company, or pooled investment
vehicle, report those assets in categories (d), (e), and (f) as applicable.

Type of Client (1) Number of (2) Fewer than 5 (3) Amount of
Client(s) Clients Regulatory Assets
under Management

(a) Individuals (other
than high net worth
individuals)

11


Type of Client

(1) Number of
Client(s)

(2) Fewer than 5
Clients

(3) Amount of
Regulatory Assets
under Management

(b) High net worth
individuals

(c) Banking or thrift
institutions

(d) Investment
companies

(e) Business
development
companies

(f) Pooled
investment vehicles
(other than
investment
companies and
business
development
companies)

(g) Pension and
profit sharing plans
(but not the plan
participants or
government pension
plans)

(h) Charitable
organizations

(i) State or municipal
government entities
(including
government pension
plans)

(j) Other investment
advisers

(k) Insurance
companies

(J) Sovereign wealth
funds and foreign
official institutions

(m) Corporations or
other businesses not
listed above

(n) Other:

12



Compensation Arrangements

E. You are compensated for your investment advisory services by (check all that apply):

(1) A percentage of assets under your management
(2) Hourly charges

O (3) Subscription fees (for a newsletter or periodical)
OO (4) Fixed fees (other than subscription fees)

(5) Commissions

(6) Performance-based fees

(7) Other (specify):

Regulatory Assets Under Management

F. (1) Do you provide continuous and regular supervisory or management services to
securities portfolios? O Yes O No

(2) If yes, what is the amount of your regulatory assets under management and total
number of accounts?

U.S. Dollar Amount Total Number of Accounts
Discretionary: (a) $ .00 (d)
Non-Discretionary: (b) $ .00 (e)
Total: (c) $ .00 (f)

Part 1A Instruction 5.b. explains how to calculate your regulatory assets under
management. You must follow these instructions carefully when completing this Item.

(3) What is the approximate amount of your total regulatory assets under management
(reported in Item 5.F.(2)(c) above) attributable to clients who are non-United States
persons?

Advisory Activities

G. What type(s) of advisory services do you provide? Check all that apply.

O (1) Financial planning services

O (2) Portfolio management for individuals and/or small businesses

O (3) Portfolio management for investment companies (as well as “business
development companies” that have made an election pursuant to section 54 of
the Investment Company Act of 1940)

O (4) Portfolio management for pooled investment vehicles (other than investment

13


companies)

O (5) Portfolio management for businesses (other than small businesses) or
institutional clients (other than registered investment companies and other
pooled investment vehicles)

O (6) Pension consulting services

O (7) Selection of other advisers (including private fund managers)

O (8) Publication of periodicals or newsletters

O (9) Security ratings or pricing services

O (10) Market timing services

O (11) Educational seminars/workshops

O (12) Other (specify):

Do not check Item 5.G.(3) unless you provide advisory services pursuant to an investment
advisory contract to an investment company registered under the Investment Company Act of
1940, including as a subadviser. If you check Item 5.G.(3), report the 811 or 814 number of
the investment company or investment companies to which you provide advice in Section
5.G.(3) of Schedule D.

H. If you provide financial planning services, to how many clients did you provide these

services during your last fiscal year?
Oo O 1-10 O 11-25 O 26-50 O 51-100 QO 101-250 O 251-500
O More than 500 — If more than 500, how many? (round to the nearest 500)

In your responses to this Item 5.H., do not include as “clients” the investors in a private fund
you advise, unless you have a separate advisory relationship with those investors.

I. (1) Do you participate in a wrap fee program? O Yes ONo

(2) If you participate in a wrap fee program, what is the amount of your regulatory assets
under management attributable to acting as:

(a) sponsor to a wrap fee program $
(b) portfolio manager for a wrap fee program? $
(c) sponsor to and portfolio manager for the same wrap fee program? $

If you report an amount in Item 5.1.(2)(c), do not report that amount in Item 5.1.(2)(a) or
Item 5.1.(2)(b).

If you are a portfolio manager for a wrap fee program, list the names of the programs,
their sponsors and related information in Section 5.1.(2) of Schedule D.

If your involvement in a wrap fee program is limited to recommending wrap fee

programs to your clients, or you advise a mutual fund that is offered through a wrap fee
program, do not check Item 5.I.(1) or enter any amounts in response to Item 5.I.(2).

14


(1) In response to Item 4.B. of Part 2A of Form ADV, do you indicate that you provide
investment advice only with respect to limited types of investments?
O Yes No

(2) Do you report client assets in Item 4.E. of Part 2A that are computed using a different
method than the method used to compute your regulatory assets under management?
O Yes No

. Separately Managed Account Clients

(1) Do you have regulatory assets under management attributable to clients other than
those listed in Item 5.D.(3)(d)-(f) (separately managed account clients)?
O Yes O No
If yes, complete Section 5.K.(1) of Schedule D.

(2) Do you engage in borrowing transactions on behalf of any of the separately managed
account clients that you advise? O Yes O No

If yes, complete Section 5.K.(2) of Schedule D.

(3) Do you engage in derivative transactions on behalf of any of the separately managed
account clients that you advise? O Yes O No

If yes, complete Section 5.K.(2) of Schedule D.

(4) After subtracting the amounts in Item 5.D.(3)(d)-(f) above from your total regulatory
assets under management, does any custodian hold ten percent or more of this
remaining amount of regulatory assets under management? L Yes O No

If yes, complete Section 5.K.(3) of Schedule D for each custodian.

[Effective May 4, 2021, Item 5.L. appears as follows, pursuant to Investment Adviser Marketing,
Investment Advisers Act Release No. 5653 (Dec. 22, 2020) [86 FR 13024 (Mar. 5, 2021)].]

. Marketing Activities

(1) Do any of your advertisements include:

(a) Performance results? O Yes O No

(b) A reference to specific investment advice provided by you (as that phrase is usedin rule
206(4)-1(a)(5))? OO Yes O No

(c) Testimonials (other than those that satisfy rule 206(4)-1(b)(4)(i1))?
15


OO Yes O No

(d) Endorsements (other than those that satisfy rule 206(4)-1(b)(4)(i))?
O Yes O No

(e) Third-party ratings? O Yes O No

(2) If you answer “yes” to L(1)(c), (d), or (e) above, do you pay or otherwise provide cash
or non-cash compensation, directly or indirectly, in connection with the use of
testimonials, endorsements, or third-party ratings? 1 Yes O No

(3) Do any of your advertisements include hypothetical performance?
O Yes O No

(4) Do any of your advertisements include predecessor performance?
O Yes O No

Item 6 Other Business Activities
In this Item, we request information about your firm’s other business activities.
A. You are actively engaged in business as a (check all that apply):

O (1) _ broker-dealer (registered or unregistered)

O (2) registered representative of a broker-dealer

(3) commodity pool operator or commodity trading advisor (whether registered or
exempt from registration)

(4) futures commission merchant

(5) real estate broker, dealer, or agent

(6) insurance broker or agent

(7) _ bank (including a separately identifiable department or division of a bank)

(8) trust company

(9) registered municipal advisor

(10) registered security-based swap dealer

(11) major security-based swap participant

(12) accountant or accounting firm

(13) lawyer or law firm

(14) other financial product salesperson (specify):

If you engage in other business using a name that is different from the names reported in
Items 1.A. or 1.B.(1), complete Section 6.A. of Schedule D.

16


B. (1) Are you actively engaged in any other business not listed in Item 6.A. (other than
giving investment advice)? O Yes O No

(2) If yes, is this other business your primary business? O Yes O No

If “yes,” describe this other business on Section 6.B.(2) of Schedule D, and if you
engage in this business under a different name, provide that name.

(3) Do you sell products or provide services other than investment advice to your
advisory clients? O Yes O No

If “yes,” describe this other business on Section 6.B.(3) of Schedule D, and if you
engage in this business under a different name, provide that name.

Item7 Financial Industry Affiliations and Private Fund Reporting

In this Item, we request information about your financial industry affiliations and activities. This
information identifies areas in which conflicts of interest may occur between you and your
clients.

A. This part of Item 7 requires you to provide information about you and your related
persons, including foreign affiliates. Your related persons are all of your advisory
affiliates and any person that is under common control with you.

You have a related person that is a (check all that apply):

(1) _ broker-dealer, municipal securities dealer, or government securities broker or
dealer (registered or unregistered)

(2) other investment adviser (including financial planners)

(3) registered municipal advisor

(4) registered security-based swap dealer

(5) major security-based swap participant

from registration)

(7) | futures commission merchant

(8) banking or thrift institution

(9) trust company

(10) accountant or accounting firm

(11) lawyer or law firm

(12) insurance company or agency

(13) pension consultant

(14) real estate broker or dealer

(15) sponsor or syndicator of limited partnerships (or equivalent), excluding pooled
investment vehicles

(16) sponsor, general partner, managing member (or equivalent) of pooled
investment vehicles

17

(6) commodity pool operator or commodity trading advisor (whether registered or exempt


Note that Item 7.A. should not be used to disclose that some of your employees perform
investment advisory functions or are registered representatives of a broker-dealer. The
number of your firm’s employees who perform investment advisory functions should be
disclosed under Item 5.B.(1). The number of your firm’s employees who are registered
representatives of a broker-dealer should be disclosed under Item 5.B.(2).

Note that if you are filing an umbrella registration, you should not check Item 7.A.(2)
with respect to your relying advisers, and you do not have to complete Section 7.A. in
Schedule D for your relying advisers. You should complete a Schedule R for each
relying adviser.

For each related person, including foreign affiliates that may not be registered or
required to be registered in the United States, complete Section 7.A. of Schedule D.

You do not need to complete Section 7.A. of Schedule D for any related person if: (1) you
have no business dealings with the related person in connection with advisory services
you provide to your clients; (2) you do not conduct shared operations with the related
person; (3) you do not refer clients or business to the related person, and the related
person does not refer prospective clients or business to you; (4) you do not share
supervised persons or premises with the related person; and (5) you have no reason to
believe that your relationship with the related person otherwise creates a conflict of
interest with your clients.

You must complete Section 7.A. of Schedule D for each related person acting as qualified
custodian in connection with advisory services you provide to your clients (other than
any mutual fund transfer agent pursuant to rule 206(4)-2(b)(1)), regardless of whether
you have determined the related person to be operationally independent under rule
206(4)-2 of the Advisers Act.

B. Are you an adviser to any private fund? O Yes O No

18


If “yes,” then for each private fund that you advise, you must complete a Section 7.B.(1)
of Schedule D, except in certain circumstances described in the next sentence and in
Instruction 6 of the Instructions to Part 1A. If you are registered or applying for
registration with the SEC or reporting as an SEC exempt reporting adviser, and another
SEC-registered adviser or SEC exempt reporting adviser reports this information with
respect to any such private fund in Section 7.B.(1) of Schedule D of its Form ADV (e.g., if
you are a subadviser), do not complete Section 7.B.(1) of Schedule D with respect to that
private fund. You must, instead, complete Section 7.B.(2) of Schedule D.

In either case, if you seek to preserve the anonymity of a private fund client by
maintaining its identity in your books and records in numerical or alphabetical code, or
similar designation, pursuant to rule 204-2(d), you may identify the private fund in
Section 7.B.(1) or 7.B.(2) of Schedule D using the same code or designation in place of
the fund’s name.

Item8 Participation or Interest in Client Transactions

In this Item, we request information about your participation and interest in your clients’
transactions. This information identifies additional areas in which conflicts of interest may occur
between you and your clients. Newly-formed advisers should base responses to these questions

on the types of participation and interest that you expect to engage in during the next year.

Like Item 7, Item 8 requires you to provide information about you and your related persons,
including foreign affiliates.

Proprietary Interest in Client Transactions

A. Do you or any related person:

Yes No

(1) buy securities for yourself from advisory clients, or sell securities
you own to advisory clients (principal transactions)?

(2) buy or sell for yourself securities (other than shares of mutual funds)
that you also recommend to advisory clients?

(3) recommend securities (or other investment products) to advisory
clients in which you or any related person has some other
proprietary (ownership) interest (other than those mentioned in
Items 8.A.(1) or (2))? Oo O

Sales Interest in Client Transactions

B. Do you or any related person:
Yes No
(1) as a broker-dealer or registered representative of a broker-dealer,
execute securities trades for brokerage customers in which advisory

19


client securities are sold to or bought from the brokerage customer

(agency cross transactions)?

(2) recommend to advisory clients, or act as a purchaser representative

for advisory clients with respect to, the purchase of securities for
which you or any related person serves as underwriter or general
or managing partner?

(3) recommend purchase or sale of securities to advisory clients for

which you or any related person has any other sales interest (other

than the receipt of sales commissions as a broker or registered
representative of a broker-dealer)?

Investment or Brokerage Discretion

C. Do you or any related person have discretionary authority to
determine the:

(1) securities to be bought or sold for a client’s account?
(2) amount of securities to be bought or sold for a client’s account?

(3) broker or dealer to be used for a purchase or sale of securities for
a client’s account?

(4) commission rates to be paid to a broker or dealer for a client's
securities transactions?

. If you answer “‘yes” to C.(3) above, are any of the brokers or dealers
related persons?

. Do you or any related person recommend brokers or dealers to
clients?

. If you answer “yes” to E. above, are any of the brokers or dealers
related persons?

. (1) Do you or any related person receive research or other products
or services other than execution from a broker-dealer or a third
party (“soft dollar benefits”) in connection with client securities
transactions?

(2) If “yes” to G.(1) above, are all the “soft dollar benefits” you or
any related persons receive eligible “research or brokerage services”
under section 28(e) of the Securities Exchange Act of 1934?

. (1) Do you or any related person, directly or indirectly, compensate
20

O O
O O
O O
Yes No
O O
O O
O O
O O
O O
O O
O O


any person that is not an employee for client referrals? Oo O

(2) Do you or any related person, directly or indirectly, provide any
employee compensation that is specifically related to obtaining
clients for the firm (cash or non-cash compensation in addition
to the employee’s regular salary)? O O

I. Do you or any related person, including any employee, directly or
indirectly, receive compensation from any person (other than you or
any related person) for client referrals? O O

In your response to Item 8.1, do not include the regular salary you pay to an employee.

In responding to Items 8.H. and 8.1, consider all cash and non-cash compensation that
you or a related person gave to (in answering Item 8.H.) or received from (in answering
Item 8.1.) any person in exchange for client referrals, including any bonus that is based,
at least in part, on the number or amount of client referrals.

Item 9 Custody
In this Item, we ask you whether you or a related person has custody of client (other than clients

that are investment companies registered under the Investment Company Act of 1940) assets and
about your custodial practices.

A. (1) Do you have custody of any advisory clients’: Yes No
(a) cash or bank accounts ? O Oo
(b) securities? O Oo

Ifyou are registering or registered with the SEC, answer “No” to Item 9.A.(1)(a) and (b)
if you have custody solely because (i) you deduct your advisory fees directly from your
clients’ accounts, or (ii) a related person has custody of client assets in connection with
advisory services you provide to clients, but you have overcome the presumption that you
are not operationally independent (pursuant to Advisers Act rule 206(4)-2(d)(5)) from the
related person.

(2) If you checked “yes” to Item 9.A.(1)(a) or (b), what is the approximate amount of
client funds and securities and total number of clients for which you have custody:

U.S. Dollar Amount Total Number of Clients
@Soo (b)
If you are registering or registered with the SEC and you have custody solely because

you deduct your advisory fees directly from your clients’ accounts, do not include the
amount of those assets and the number of those clients in your response to Item 9.A.(2).

21


If your related person has custody of client assets in connection with advisory services
you provide to clients, do not include the amount of those assets and the number of those
clients in your response to Item 9.A.(2). Instead, include that information in your
response to Item 9.B.(2).

. (1) In connection with advisory services you provide to clients, do any of your related

persons have custody of any of your advisory clients’: Yes No
(a) cash or bank accounts? O Oo
(b) securities? Oo O

You are required to answer this item regardless of how you answered Item 9.A.(1)(a) or

(b).

(2) If you checked “yes” to Item 9.B.(1)(a) or (b), what is the approximate amount of
client funds and securities and total number of clients for which your related
persons have custody:

U.S. Dollar Amount Total Number of Clients

(a)$__ (b)

. If you or your related persons have custody of client funds or securities in connection
with advisory services you provide to clients, check all the following that apply:

O (1) A qualified custodian(s) sends account statements at least quarterly to the
investors in the pooled investment vehicle(s) you manage.

(2) An independent public accountant audits annually the pooled investment
vehicle(s) that you manage and the audited financial statements are distributed
to the investors in the pools.

O (3) An independent public accountant conducts an annual surprise examination of
client funds and securities.

O (4) An independent public accountant prepares an internal control report with
respect to custodial services when you or your related persons are qualified
custodians for client funds and securities.

If you checked Item 9.C.(2), C.(3) or C.(4), list in Section 9.C. of Schedule D the
accountants that are engaged to perform the audit or examination or prepare an internal
control report. (If you checked Item 9.C.(2), you do not have to list auditor information
in Section 9.C. of Schedule D if you already provided this information with respect to the
private funds you advise in Section 7.B.(1) of Schedule D).

22


D. Do you or your related person(s) act as qualified custodians for your clients in

connection with advisory services you provide to clients?
Yes No

(1) you act as a qualified custodian
(2) your related person(s) act as qualified custodian(s) O O

If you checked “yes” to Item 9.D.(2), all related persons that act as qualified custodians
(other than any mutual fund transfer agent pursuant to rule 206(4)-2(b)(1)) must be

identified in Section 7.A. of Schedule D, regardless of whether you have determined the
related person to be operationally independent under rule 206(4)-2 of the Advisers Act.

E. If you are filing your annual updating amendment and you were subject to a surprise
examination by an independent public accountant during your last fiscal year, provide the
date (MM/YYYY) the examination commenced:

F. If you or your related persons have custody of client funds or securities, how many
persons, including, but not limited to, you and your related persons, act as qualified
custodians for your clients in connection with advisory services you provide to clients?

Item 10 Control Persons

In this Item, we ask you to identify every person that, directly or indirectly, controls you. If you
are filing an umbrella registration, the information in Item 10 should be provided for the filing
adviser only.

If you are submitting an initial application or report, you must complete Schedule A and
Schedule B. Schedule A asks for information about your direct owners and executive
officers. Schedule B asks for information about your indirect owners. If this is an
amendment and you are updating information you reported on either Schedule A or Schedule
B (or both) that you filed with your initial application or report, you must complete Schedule
Cc

A. Does any person not named in Item 1.A. or Schedules A, B, or C, directly or indirectly,
control your management or policies? O Yes O No

If yes, complete Section 10.A. of Schedule D.
B. If any person named in Schedules A, B, or C or in Section 10.A. of Schedule D is a

public reporting company under Sections 12 or 15(d) of the Securities Exchange Act of
1934, please complete Section 10.B. of Schedule D.

Item 11 Disclosure Information

In this Item, we ask for information about your disciplinary history and the disciplinary history
of all your advisory affiliates. We use this information to determine whether to grant your

23


application for registration, to decide whether to revoke your registration or to place limitations
on your activities as an investment adviser, and to identify potential problem areas to focus on
during our on-site examinations. One event may result in “yes” answers to more than one of the
questions below. In accordance with General Instruction 5 to Form ADV, “you” and “your”
include the filing adviser and all relying advisers under an umbrella registration.

Your advisory affiliates are: (1) all of your current employees (other than employees performing
only clerical, administrative, support or similar functions); (2) all of your officers, partners, or
directors (or any person performing similar functions); and (3) all persons directly or indirectly
controlling you or controlled by you. If you are a “separately identifiable department or
division” (SID) of a bank, see the Glossary of Terms to determine who your advisory affiliates
are.

Ifyou are registered or registering with the SEC or if you are an exempt reporting adviser, you
may limit your disclosure of any event listed in Item 11 to ten years following the date of the
event. If you are registered or registering with a state, you must respond to the questions as
posed; you may, therefore, limit your disclosure to ten years following the date of an event only
in responding to Items 11.A.(1), 11.A.(2), 11.B.(1), 11.B.(2), 11.D.(4), and 11.H.(1)(a). For
purposes of calculating this ten-year period, the date of an event is the date the final order,
judgment, or decree was entered, or the date any rights of appeal from preliminary orders,
judgments, or decrees lapsed.

You must complete the appropriate Disclosure Reporting Page (“DRP”’) for “yes” answers to the
questions in this Item 11.

Yes No
Do any of the events below involve you or any of your supervised persons?
For “yes” answers to the following questions, complete a Criminal Action DRP:
Yes No
A. In the past ten years, have you or any advisory affiliate:
(1) been convicted of or pled guilty or nolo contendere (“no contest”)
in a domestic, foreign, or military court to any felony? Oo O
(2) been charged with any felony? Oo O

Ifyou are registered or registering with the SEC, or if you are reporting as an exempt
reporting adviser, you may limit your response to Item 11.A.(2) to charges that are
currently pending.

B. In the past ten years, have you or any advisory affiliate:

(1) been convicted of or pled guilty or nolo contendere (“no contest”)
in a domestic, foreign, or military court to a misdemeanor involving:

24


investments or an investment-related business, or any fraud, false

statements, or omissions, wrongful taking of property, bribery,

perjury, forgery, counterfeiting, extortion, or a conspiracy to commit

any of these offenses? Oo O

(2) been charged with a misdemeanor listed in Item 11.B.(1)? O O
Ifyou are registered or registering with the SEC, or if you are reporting as an exempt
reporting adviser, you may limit your response to Item 11.B.(2) to charges that are

currently pending.

For “tyes” answers to the following questions, complete a Regulatory Action DRP:
Yes No

C. Has the SEC or the Commodity Futures Trading Commission
(CFTC) ever:

(1) found you or any advisory affiliate to have made a false statement
or omission?

(2) found you or any advisory affiliate to have been involved ina
violation of SEC or CFTC regulations or statutes?

(3) found you or any advisory affiliate to have been a cause of an
investment-related business having its authorization to do business
denied, suspended, revoked, or restricted? oO oO

(4) entered an order against you or any advisory affiliate in connection
with investment-related activity?

(5) imposed a civil money penalty on you or any advisory affiliate, or
ordered you or any advisory affiliate to cease and desist from any
activity?

D. Has any other federal regulatory agency, any state regulatory agency,
or any foreign financial regulatory authority:

(1) ever found you or any advisory affiliate to have made a false
statement or omission, or been dishonest, unfair, or unethical?

(2) ever found you or any advisory affiliate to have been involved in
a violation of investment-related regulations or statutes?

(3) ever found you or any advisory affiliate to have been a cause of an
investment-related business having its authorization to do business
denied, suspended, revoked, or restricted? O O

25


(4) in the past ten years, entered an order against you or any advisory
affiliate in connection with an investment-related activity? O

(5) ever denied, suspended, or revoked your or any advisory affiliate ’s
registration or license, or otherwise prevented you or any advisory
affiliate, by order, from associating with an investment-related
business or restricted your or any advisory affiliate ’s activity? Oo

E. Has any self-regulatory organization or commodities exchange ever:

(1) found you or any advisory affiliate to have made a false statement
or omission? im)

(2) found you or any advisory affiliate to have been involved in a
violation of its rules (other than a violation designated as a
“minor rule violation” under a plan approved by the SEC)? u

(3) found you or any advisory affiliate to have been the cause of an
investment-related business having its authorization to do business
denied, suspended, revoked, or restricted? u

(4) disciplined you or any advisory affiliate by expelling or
suspending you or the advisory affiliate from membership,
barring or suspending you or the advisory affiliate from association
with other members, or otherwise restricting your or the advisory
affiliate’s activities? O

F. Has an authorization to act as an attorney, accountant, or federal
contractor granted to you or any advisory affiliate ever been revoked

or suspended?

G. Are you or any advisory affiliate now the subject of any regulatory
proceeding that could result in a “yes” answer to any part of Item 11.C.,
11.D., or 11.E.? oO

For “yes” answers to the following questions, complete a Civil Judicial Action DRP:

Yes
H. (1) Has any domestic or foreign court:
(a) in the past ten years, enjoined you or any advisory affiliate in
connection with any investment-related activity?
(b) ever found that you or any advisory affiliate were involved in
a violation of investment-related statutes or regulations? O

26



(c) ever dismissed, pursuant to a settlement agreement, an
investment-related civil action brought against you or any
advisory affiliate by a state or foreign financial regulatory
authority? Oo O

(2) Are you or any advisory affiliate now the subject of any civil
proceeding that could result in a “yes” answer to any part of
Item 11.H.(1)? Oo O

Item 12 Small Businesses

The SEC is required by the Regulatory Flexibility Act to consider the effect of its regulations on
small entities. In order to do this, we need to determine whether you meet the definition of
“small business” or “small organization” under rule 0-7.

Answer this Item 12 only if you are registered or registering with the SEC and you indicated in
response to Item 5.F.(2)(c) that you have regulatory assets under management of less than $25
million. You are not required to answer this Item 12 if you are filing for initial registration as a
state adviser, amending a current state registration, or switching from SEC to state registration.

For purposes of this Item 12 only:

e Total Assets refers to the total assets of a firm, rather than the assets managed on behalf
of clients. In determining your or another person’s total assets, you may use the total assets
shown on a current balance sheet (but use total assets reported on a consolidated balance
sheet with subsidiaries included, if that amount is larger).

¢ Control means the power to direct or cause the direction of the management or policies of
a person, whether through ownership of securities, by contract, or otherwise. Any person
that directly or indirectly has the right to vote 25 percent or more of the voting securities, or
is entitled to 25 percent or more of the profits, of another person is presumed to control the

other person.
Yes No
A. Did you have total assets of $5 million or more on the last day of your
most recent fiscal year? Oo Oo
If “yes,” you do not need to answer Items 12.B. and 12.C.
B. Do you:
(1) control another investment adviser that had regulatory assets under
management (calculated in response to Item 5.F.(2)(c) of Form
ADV) of $25 million or more on the last day of its most recent
fiscal year? O Oo

27


(2) control another person (other than a natural person) that had total
assets of $5 million or more on the last day of its most recent
fiscal year?

C. Are you:

(1) controlled by or under common control with another investment
adviser that had regulatory assets under management (calculated
in response to Item 5.F.(2)(c) of Form ADV) of $25 million or
more on the last day of its most recent fiscal year?

(2) controlled by or under common control with another person

(other than a natural person) that had total assets of $5 million
or more on the last day of its most recent fiscal year?

28
"""
# Initialize session state for part1_answer, sql_query, and sql_result if they don't already exist
if "part1_answer" not in st.session_state:
    st.session_state.part1_answer = ""
if "sql_query" not in st.session_state:
    st.session_state.sql_query = ""
if "sql_result" not in st.session_state:
    st.session_state.sql_result = ""

# Input question for Part 1
# Define sample questions for the dropdown
sample_questions = [
    "What is the total number of assets under management of the investment advisers, in trillion dollars?",
    "What is the number of advisers with each more than one million clients?",
    "What fraction of advisers provide portfolio management services to their clients?",
    "What is the total assets under custody of advisers, in trillion dollars?",
    "What fraction of advisers have custody of clients' cash or securities?",
    "What is the total number of small registered investment advisers?",
    "How many employees (both full-time and part-time) does American Investors Co have?",
    "How many advisers have over 60% of clients that are non-United States persons?",
    "What percentage of advisers participate in a wrap fee program?",
    "What is the total number of advisers who are compensated for their services with commissions?"
]
selected_sample = st.selectbox("Choose a sample question or type your own:", ["Type your own question..."] + sample_questions)

# Determine if the user selected a sample question or wants to type their own
question = st.text_input("Enter your question about the document:",
                         value=selected_sample if selected_sample != "Type your own question..." else "",
                         placeholder="Type your question here...")

if st.button("Run Part 1"):
    if question and extracted_text:
        st.session_state.part1_answer = query_openai_part1(extracted_text, question)
st.text_area("Part 1 Answer (Relevant Items from Form ADV)", st.session_state.part1_answer, height=200, disabled=True)

# Editable Part 1 answer confirmation for Part 2
st.header("Part 2: Generate SQL Query")
confirmed_part1_answer = st.text_area("Confirm or Edit Part 1 Answer", st.session_state.part1_answer, height=200)
if st.button("Run Part 2"):
    if confirmed_part1_answer:
        st.session_state.sql_query = generate_sql_query(question, confirmed_part1_answer)
st.text_area("Generated SQL Query", st.session_state.sql_query, height=100, disabled=True)

# Editable SQL query confirmation for Part 3
st.header("Part 3: Execute SQL Query")
confirmed_sql_query = st.text_area("Confirm or Edit SQL Query", st.session_state.sql_query, height=100)
if st.button("Run Part 3"):
    if confirmed_sql_query:
        st.session_state.sql_result = execute_sql_query(confirmed_sql_query)
        st.write("Query Result:", st.session_state.sql_result)

        if st.session_state.sql_result is not None:
            final_answer = get_final_answer_from_llm(question, st.session_state.sql_result)
            st.write("Final Answer:", final_answer)
