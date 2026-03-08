# Web-Based Academic Biodata Management System

A production-ready Flask application for managing student academic history across 8 semesters. It features a unified data integration system that parses disparate PDFs and Excel files to merge attendance and marks into a single student biodata profile based on **Register Number** and **Subject Codes**.

## 🚀 Key Features
-   **Integrated Data Parser**: Upload multiple PDFs/Excels at once. The system automatically identifies "Reg No" columns and "Subject Code" headers (e.g., MAT203) to update student records.
-   **Teacher Dashboard**:
    -   Semester-wise filtering (S1 to S8).
    -   Visual alerts (RED background) for students with attendance below 75%.
    -   Unified Biodata view with history of all 8 semesters.
-   **Student Module**:
    -   View personal integrated academic records.
    -   Self-service profile updates (Contacts, Address).
-   **Multi-Semester Architecture**: Dedicated storage and views for data from S1 through S8.

## 🛠 Prerequisites
-   Python 3.8 or higher
-   Pip (Python package manager)

## 📥 Installation

1.  **Extract the project files** to your desired directory.

2.  **Install dependencies**:
    bash
    pip install -r requirements.txt

## 🏃 How to Run

1.  **Initialize and start the server**:
    bash
    python app.py

2.  **Access the application**:
    Open your browser and go to `http://127.0.0.1:5000`

## 🔑 Default Credentials
-   **Teacher (Admin)**:
    -   Username: `admin`
    -   Password: `admin123`
-   **Student (Example)**:
    -   Username: `KTE21CS001`
    -   Password: `student123`

## 📁 File Structure
-   `app.py`: Core Flask application and database models.
-   `utils/parsers.py`: Logic for extracting data from PDF/Excel and linking via Subject Codes.
-   `templates/`: HTML structure split by Teacher and Student roles.
-   `static/`: CSS for the sidebar and attendance "red-bar" styling.
-   `uploads/`: Temporary storage for uploaded PDF/Excel files.

## 📝 Usage for Teachers
1.  Navigate to **Upload Data**.
2.  Select the Target Semester (e.g., S3).
3.  Choose multiple files (e.g., `attendance.xlsx`, `results_pdf.pdf`, `internals.csv`).
4.  Click **Process**.
5.  View the results in **Dashboard** (check for red highlights) or **Attendance** list.
