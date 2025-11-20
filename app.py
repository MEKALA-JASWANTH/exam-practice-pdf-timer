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
    Extract questions from PDF file.
    This is a basic implementation - you may need to customize based on your PDF format.
    """
    questions = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            # Split by common question patterns
            # This pattern looks for: "1.", "Q1.", "Question 1:", etc.
            question_pattern = r'(?:^|\n)(?:\d+\.|Q\.|Q\s*\d+\.|Question\s*\d+:)[^\n]*'
            
            parts = re.split(question_pattern, full_text)
            
            # First part is usually before any questions, so skip it
            for i, part in enumerate(parts[1:], 1):
                if part.strip():
                    questions.append({
                        'id': i,
                        'text': part.strip()[:500],  # Limit to 500 chars per question
                        'options': []  # Add option parsing if needed
                    })
    
    except Exception as e:
        print(f"Error extracting questions: {e}")
        return []
    
    return questions

def save_questions_to_file(session_id, questions):
    """Save questions to a JSON file instead of session"""
    filepath = os.path.join(app.config['DATA_FOLDER'], f'{session_id}.json')
    with open(filepath, 'w') as f:
        json.dump(questions, f)

def load_questions_from_file(session_id):
    """Load questions from JSON file"""
    filepath = os.path.join(app.config['DATA_FOLDER'], f'{session_id}.json')
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
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
