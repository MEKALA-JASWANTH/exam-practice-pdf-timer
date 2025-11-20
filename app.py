from flask import Flask, render_template, request, redirect, url_for, session
import pdfplumber
import os
import re
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

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
            question_pattern = r'(?:^|\n)(?:Q\.?\s*\d+|Question\s*\d+|\d+\.)'
            
            parts = re.split(question_pattern, full_text)
            
            # First part is usually before any questions, so skip it
            for i, part in enumerate(parts[1:], 1):
                if part.strip():
                    questions.append({
                        'id': i,
                        'question': part.strip()[:500]  # Limit to 500 chars per question
                    })
    
    except Exception as e:
        print(f"Error extracting questions: {e}")
        return []
    
    return questions

@app.route('/')
def index():
    return render_template('index.html')

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
        
        # Store in session
        session['questions'] = questions
        session['current_question'] = 0
        session['exam_duration'] = int(request.form.get('duration', 60))  # Default 60 minutes
        
        return redirect(url_for('exam'))
    
    return redirect(url_for('index'))

@app.route('/exam')
def exam():
    questions = session.get('questions', [])
    current_idx = session.get('current_question', 0)
    duration = session.get('exam_duration', 60)
    
    if not questions:
        return redirect(url_for('index'))
    
    return render_template('exam.html', 
                         question=questions[current_idx] if current_idx < len(questions) else None,
                         current=current_idx + 1,
                         total=len(questions),
                         duration=duration)

@app.route('/next')
def next_question():
    current = session.get('current_question', 0)
    questions = session.get('questions', [])
    
    if current < len(questions) - 1:
        session['current_question'] = current + 1
    
    return redirect(url_for('exam'))

@app.route('/previous')
def previous_question():
    current = session.get('current_question', 0)
    
    if current > 0:
        session['current_question'] = current - 1
    
    return redirect(url_for('exam'))

@app.route('/finish')
def finish_exam():
    # Clear session
    session.clear()
    return render_template('finish.html')

if __name__ == '__main__':
    app.run(debug=True)
