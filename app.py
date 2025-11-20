from flask import Flask, render_template, request, redirect, url_for, session
import pdfplumber
import os
import re
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['DATA_FOLDER'] = 'data'  # Store questions here

# Create folders if they don't exist
for folder in [app.config['UPLOAD_FOLDER'], app.config['DATA_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_questions_from_pdf(pdf_path):
    """
    Extract questions from PDF file - IMPROVED for Government Exam PDFs.
    Handles formats like SSC CGL, IBPS PO, CHSL, etc.
    """
    questions = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            # Multiple question patterns for government exams
            # Pattern 1: Q.1, Q.2, Q.3... (Most common)
            # Pattern 2: Q1., Q2., Q3...
            # Pattern 3: Question 1, Question 2...
            question_patterns = [
                r'Q\.\d+',  # Matches Q.1, Q.2, Q.3
                r'Q\d+\.',  # Matches Q1., Q2., Q3.
                r'Question\s+\d+',  # Matches Question 1, Question 2
            ]
            
            # Try each pattern
            for pattern in question_patterns:
                matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
                if len(matches) > 5:  # If we found at least 5 questions, use this pattern
                    break
            
            if not matches:
                # Fallback: Split by newlines and create questions
                lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                for i, line in enumerate(lines[:100]):  # Limit to first 100 lines
                    if len(line) > 10:  # Only meaningful lines
                        questions.append({
                            'id': i + 1,
                            'text': line[:800],  # Limit to 800 chars
                            'options': []
                        })
                return questions[:50]  # Return max 50 questions
            
            # Extract questions based on found pattern
            for i in range(len(matches)):
                question_start = matches[i].end()
                question_end = matches[i+1].start() if i+1 < len(matches) else len(full_text)
                
                question_text = full_text[question_start:question_end].strip()
                
                # Clean up question text
                question_text = re.sub(r'\s+', ' ', question_text)  # Remove extra spaces
                question_text = re.sub(r'[\n\r]+', ' ', question_text)  # Remove newlines
                
                # Extract options (Ans 1., Ans 2., etc. OR just 1., 2., 3., 4.)
                options = []
                option_pattern = r'(?:Ans\s+)?(\d+)\.\s*([^\d]{1,200}?)(?=(?:Ans\s+)?\d+\.|$)'
                option_matches = re.findall(option_pattern, question_text[:1000])
                
                if option_matches:
                    options = [opt[1].strip() for opt in option_matches[:4]]  # Max 4 options
                    # Remove options from question text
                    for opt in option_matches:
                        question_text = question_text.replace(f"{opt[0]}. {opt[1]}", "")
                        question_text = question_text.replace(f"Ans {opt[0]}. {opt[1]}", "")
                
                # Limit question length
                if len(question_text) > 800:
                    question_text = question_text[:800] + "..."
                
                if question_text.strip():  # Only add non-empty questions
                    questions.append({
                        'id': i + 1,
                        'text': question_text.strip(),
                        'options': options
                    })
                
                # Limit to 100 questions max
                if len(questions) >= 100:
                    break
    
    except Exception as e:
        print(f"Error extracting questions: {e}")
        # Return a sample question in case of error
        return [{
            'id': 1,
            'text': f"Error reading PDF: {str(e)}. Please try a different PDF or check the format.",
            'options': []
        }]
    
    return questions if questions else [{
        'id': 1,
        'text': 'No questions found in PDF. The PDF format might not be supported. Please try a text-based PDF.',
        'options': []
    }]

def save_questions_to_file(session_id, questions):
    """Save questions to a JSON file instead of session"""
    filepath = os.path.join(app.config['DATA_FOLDER'], f'{session_id}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

def load_questions_from_file(session_id):
    """Load questions from JSON file"""
    filepath = os.path.join(app.config['DATA_FOLDER'], f'{session_id}.json')
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extract questions
        questions = extract_questions_from_pdf(filepath)
        
        # Generate unique session ID
        import uuid
        session_id = str(uuid.uuid4())
        
        # Store questions in file instead of session
        save_questions_to_file(session_id, questions)
        
        # Store only the session ID and metadata in session
        session['session_id'] = session_id
        session['current_question'] = 0
        session['exam_duration'] = int(request.form.get('timer', 60))  # Default 60 minutes
        
        return redirect(url_for('exam'))
    
    return redirect(url_for('index'))

@app.route('/exam')
def exam():
    session_id = session.get('session_id')
    if not session_id:
        return redirect(url_for('index'))
    
    questions = load_questions_from_file(session_id)
    if not questions:
        return redirect(url_for('index'))
    
    current_idx = session.get('current_question', 0)
    duration = session.get('exam_duration', 60)
    
    return render_template('exam.html',
                         questions=questions,
                         current=current_idx + 1,
                         total=len(questions),
                         duration=duration)

@app.route('/next')
def next_question():
    session_id = session.get('session_id')
    current = session.get('current_question', 0)
    
    questions = load_questions_from_file(session_id)
    if questions and current < len(questions) - 1:
        session['current_question'] = current + 1
    
    return redirect(url_for('exam'))

@app.route('/previous')
def previous_question():
    current = session.get('current_question', 0)
    
    if current > 0:
        session['current_question'] = current - 1
    
    return redirect(url_for('exam'))

@app.route('/submit', methods=['POST'])
def finish_exam():
    # Clear session data
    session_id = session.get('session_id')
    if session_id:
        # Optionally delete the questions file
        filepath = os.path.join(app.config['DATA_FOLDER'], f'{session_id}.json')
        if os.path.exists(filepath):
            os.remove(filepath)
    
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
