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
    Handles formats like SSC CGL, IBPS PO, CHSL exams.
    """
    questions = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"
            
            # Multiple patterns to detect different question formats
            # Pattern 1: Q.1, Q.2, Q.3 (SSC CGL/CHSL style)
            # Pattern 2: Q1., Q2., Q3. (IBPS style) 
            # Pattern 3: Question followed by number
            patterns = [
                r'Q\.(\d+)\s+(.*?)(?=Q\.\d+|Ans\s*\d+|$)',
                r'Q(\d+)\.\s+(.*?)(?=Q\d+\.|Ans\s*\d+|$)',
                r'Question\s+(\d+)(?:.*?\n)(.*?)(?=Question\s+\d+|Ans|$)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, full_text, re.DOTALL)
                if matches and len(matches) > 0:
                    print(f"Found {len(matches)} questions with pattern: {pattern}")
                    break
            
            if not matches:
                # Fallback: Try to extract by splitting on common patterns
                questions = extract_by_splitting(full_text)
                return questions[:100]  # Limit to 100 questions
            
            for match in matches:
                if len(match) == 2:
                    q_num, content = match
                    
                    # Clean up the content
                    content = content.strip()
                    
                    # Extract question text and options
                    # Look for "Ans" keyword to separate question from options
                    ans_match = re.search(r'(.*?)\s*Ans\s*[:\s]*(.*)', content, re.DOTALL)
                    
                    if ans_match:
                        question_text = ans_match.group(1).strip()
                        options_text = ans_match.group(2).strip()
                    else:
                        # If no "Ans" keyword, treat first part as question
                        parts = content.split('\n', 1)
                        question_text = parts[0].strip()
                        options_text = parts[1].strip() if len(parts) > 1 else ""
                    
                    # Extract options (Ans 1., Ans 2., etc. or 1., 2., 3., 4.)
                    options = []
                    option_patterns = [
                        r'Ans\s*(\d+)[\.:)]\s*([^\n\d]+(?:\n(?!Ans\s*\d)[^\n]+)*)',
                        r'(\d+)[\.:)]\s*([^\n\d]+(?:\n(?!\d+[\.:)])[^\n]+)*)'
                    ]
                    
                    for opt_pattern in option_patterns:
                        option_matches = re.findall(opt_pattern, options_text)
                        if option_matches and len(option_matches) >= 3:
                            options = [opt[1].strip().replace('\n', ' ') for opt in option_matches]
                            break
                    
                    # Only add if we have valid question and at least 2 options
                    if question_text and len(question_text) > 10 and len(options) >= 2:
                        # Limit question text to reasonable length
                        if len(question_text) > 800:
                            question_text = question_text[:800] + "..."
                        
                        questions.append({
                            'question': question_text,
                            'options': options[:4]  # Maximum 4 options
                        })
                        
                        # Limit to 100 questions
                        if len(questions) >= 100:
                            break
        
        if not questions:
            return [{
                'question': 'No questions could be extracted from this PDF. Please ensure the PDF contains text (not images) and follows standard question format.',
                'options': ['Try another PDF', 'Check PDF format', 'Contact support', 'Go back']
            }]
        
        return questions
        
    except Exception as e:
        print(f"Error extracting questions: {str(e)}")
        return [{
            'question': f'Error processing PDF: {str(e)}',
            'options': ['Try again', 'Upload different file', 'Check file format', 'Go back']
        }]

def extract_by_splitting(text):
    """
    Fallback method: Extract by splitting on patterns
    """
    questions = []
    
    # Split by common section markers
    lines = text.split('\n')
    current_question = None
    current_options = []
    
    for line in lines:
        line = line.strip()
        
        # Check if this is a question line
        if re.match(r'^Q\.?\s*\d+', line) or re.match(r'^Question\s+\d+', line):
            # Save previous question if exists
            if current_question and current_options:
                questions.append({
                    'question': current_question,
                    'options': current_options[:4]
                })
            
            # Start new question
            current_question = re.sub(r'^Q\.?\s*\d+\s*', '', line)
            current_options = []
        
        # Check if this is an option line
        elif re.match(r'^[1-4][\.:)]', line) or re.match(r'^Ans\s*[1-4]', line):
            option_text = re.sub(r'^(?:Ans\s*)?[1-4][\.:)]\s*', '', line)
            if option_text:
                current_options.append(option_text)
        
        # Continuation of question or option
        elif current_question and not current_options:
            current_question += " " + line
    
    # Add last question
    if current_question and current_options:
        questions.append({
            'question': current_question,
            'options': current_options[:4]
        })
    
    return questions

def save_questions_to_file(session_id, questions):
    """Save questions to a JSON file"""
    filepath = os.path.join(app.config['DATA_FOLDER'], f"{session_id}.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

def load_questions_from_file(session_id):
    """Load questions from a JSON file"""
    filepath = os.path.join(app.config['DATA_FOLDER'], f"{session_id}.json")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'pdf' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['pdf']
    duration = request.form.get('duration', 30)
    
    if file.filename == '':
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extract questions
        questions = extract_questions_from_pdf(filepath)
        
        # Generate session ID and save questions
        import uuid
        session_id = str(uuid.uuid4())
        save_questions_to_file(session_id, questions)
        
        # Store minimal data in session
        session['session_id'] = session_id
        session['current_question'] = 0
        session['duration'] = int(duration)
        
        # Clean up uploaded file
        try:
            os.remove(filepath)
        except:
            pass
        
        return redirect(url_for('exam'))
    
    return redirect(url_for('index'))

@app.route('/exam')
def exam():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    
    session_id = session['session_id']
    questions = load_questions_from_file(session_id)
    
    if not questions:
        return redirect(url_for('index'))
    
    current = session.get('current_question', 0)
    duration = session.get('duration', 30)
    
    return render_template('exam.html', 
                         question=questions[current],
                         question_num=current + 1,
                         total_questions=len(questions),
                         duration=duration)

@app.route('/next', methods=['POST'])
def next_question():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    
    session_id = session['session_id']
    questions = load_questions_from_file(session_id)
    
    if not questions:
        return redirect(url_for('index'))
    
    current = session.get('current_question', 0)
    
    if current < len(questions) - 1:
        session['current_question'] = current + 1
    
    return redirect(url_for('exam'))

@app.route('/previous', methods=['POST'])
def previous_question():
    if 'session_id' not in session:
        return redirect(url_for('index'))
    
    current = session.get('current_question', 0)
    
    if current > 0:
        session['current_question'] = current - 1
    
    return redirect(url_for('exam'))

@app.route('/submit', methods=['POST'])
def submit():
    # Clean up session data
    if 'session_id' in session:
        session_id = session['session_id']
        filepath = os.path.join(app.config['DATA_FOLDER'], f"{session_id}.json")
        try:
            os.remove(filepath)
        except:
            pass
    
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
