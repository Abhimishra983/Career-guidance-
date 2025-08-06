from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import openai
import sqlite3
import os
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import werkzeug.exceptions 

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super_secret_key_should_be_in_env")

# OpenAI API Key
openai.api_key = os.getenv("OPENAI_API_KEY")

ALLOWED_TOPICS = ["resume", "interview", "career", "job", "mock"]

# ======= Database Utilities =======
def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

# ======= Initialize DB =======
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Drop tables in reverse order of dependency to avoid foreign key constraint errors
        cursor.execute("DROP TABLE IF EXISTS test_answers")
        cursor.execute("DROP TABLE IF EXISTS test_questions")
        cursor.execute("DROP TABLE IF EXISTS test_sessions")
        cursor.execute("DROP TABLE IF EXISTS interview_answers")
        cursor.execute("DROP TABLE IF EXISTS interview_questions_mapping")
        cursor.execute("DROP TABLE IF EXISTS interviews")
        cursor.execute("DROP TABLE IF EXISTS interview_questions")
        cursor.execute("DROP TABLE IF EXISTS user_progress")
        cursor.execute("DROP TABLE IF EXISTS users")
        cursor.execute("DROP TABLE IF EXISTS jobs")  # Added jobs table drop
        cursor.execute("DROP TABLE IF EXISTS careers")

        # Create tables in order of dependency
        cursor.execute('''
            CREATE TABLE careers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE user_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                last_activity TEXT,
                progress_data TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                description TEXT,
                requirements TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                career_id INTEGER,
                FOREIGN KEY(career_id) REFERENCES careers(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE interview_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                career_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                question_type TEXT NOT NULL,
                difficulty_level TEXT NOT NULL,
                ideal_answer TEXT,
                FOREIGN KEY(career_id) REFERENCES careers(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE interviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                career_id INTEGER NOT NULL,
                difficulty TEXT NOT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                overall_score REAL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(career_id) REFERENCES careers(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE interview_questions_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interview_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                FOREIGN KEY(interview_id) REFERENCES interviews(id),
                FOREIGN KEY(question_id) REFERENCES interview_questions(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE interview_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interview_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                answer_text TEXT,
                is_audio BOOLEAN DEFAULT 0,
                audio_path TEXT,
                timestamp DATETIME NOT NULL,
                score REAL,
                feedback TEXT,
                FOREIGN KEY(interview_id) REFERENCES interviews(id),
                FOREIGN KEY(question_id) REFERENCES interview_questions(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE test_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                topic TEXT,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                status TEXT NOT NULL,
                score INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE test_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_session_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                question_order INTEGER NOT NULL,
                FOREIGN KEY(test_session_id) REFERENCES test_sessions(id),
                FOREIGN KEY(question_id) REFERENCES interview_questions(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE test_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_session_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                answer TEXT NOT NULL,
                is_correct BOOLEAN NOT NULL,
                answered_at DATETIME NOT NULL,
                FOREIGN KEY(test_session_id) REFERENCES test_sessions(id),
                FOREIGN KEY(question_id) REFERENCES interview_questions(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Insert sample data
        cursor.execute('''
            INSERT INTO careers (name, description) VALUES 
            ('Software Engineering', 'Development of software applications and systems'),
            ('Data Science', 'Extracting insights from complex data'),
            ('Product Management', 'Overseeing product development and strategy'),
            ('UX/UI Design', 'Designing user interfaces and experiences'),
            ('Digital Marketing', 'Marketing products and services digitally')
        ''')
        
        cursor.execute('''
            INSERT INTO jobs (title, company, location, description, requirements, career_id)
            VALUES 
            ('Software Engineer', 'Tech Corp', 'Remote', 'Develop amazing software', 'Python, Flask, SQL', 1),
            ('Data Scientist', 'Data Insights', 'New York', 'Analyze complex datasets', 'Python, ML, Statistics', 2),
            ('UX Designer', 'Creative Solutions', 'San Francisco', 'Design user interfaces', 'Figma, UI/UX principles', 4)
        ''')
        
        cursor.execute('''
            INSERT INTO interview_questions 
            (career_id, question, question_type, difficulty_level, ideal_answer) VALUES
            (1, 'Please introduce yourself.', 'behavioral', 'beginner', 'A concise professional introduction including education and relevant experience.'),
            (1, 'Explain the concept of object-oriented programming.', 'technical', 'beginner', 'Explanation should include encapsulation, inheritance, and polymorphism with examples.'),
            (1, 'How would you approach debugging a complex issue?', 'problem-solving', 'intermediate', 'Should mention systematic approach: reproduce, isolate, identify, fix, test.'),
            (1, 'Describe your experience with version control systems.', 'technical', 'beginner', 'Mention specific systems like Git and workflows like feature branching.'),
            (1, 'What design patterns have you used in your projects?', 'technical', 'intermediate', 'Should mention common patterns like Singleton, Observer, Factory with context.'),
            (1, 'How do you optimize application performance?', 'technical', 'advanced', 'Should mention profiling, database optimization, caching strategies, etc.'),
            (1, 'Tell me about a challenging project you worked on.', 'behavioral', 'intermediate', 'Should demonstrate problem-solving and teamwork skills.')
        ''')
        
        conn.commit()
    except Exception as e:
        app.logger.error(f"Database initialization error: {str(e)}")
        raise
    finally:
        conn.close()

init_db()

# ======= Auth & Home Routes =======
@app.route('/')
def home():
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    
    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", 
            (session['user_email'],)
        ).fetchone()
        
        if not user:
            session.clear()
            return redirect(url_for('register_page'))
        
        return render_template('index.html',
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'),
                            user_data={
                                'join_date': user['created_at'] if user['created_at'] else 'Unknown',
                                'last_login': user['last_activity'] if user['last_activity'] else 'Never'
                            })
    except Exception as e:
        app.logger.error(f"Home route error: {str(e)}")
        return render_template('error.html', message="An error occurred loading your dashboard")
    finally:
        conn.close()

@app.route('/register', endpoint='register_page')
def register():
    session.clear()
    return render_template('register.html')

@app.route('/logout')
def logout():
    if session.get('user_email'):
        try:
            conn = get_db_connection()
            conn.execute(
                "UPDATE users SET last_activity = ? WHERE email = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session['user_email'])
            )
            conn.commit()
        except Exception as e:
            app.logger.error(f"Logout error: {str(e)}")
        finally:
            conn.close()
    
    session.clear()
    return redirect(url_for('register_page'))

@app.route('/api/login', methods=['POST'])
def login_post():
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password required."}), 400

    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", 
            (email,)
        ).fetchone()
        
        if not user or not check_password_hash(user['password'], password):
            return jsonify({"success": False, "message": "Invalid credentials."}), 401

        # Update last login time
        conn.execute(
            "UPDATE users SET last_activity = ? WHERE email = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), email)
        )
        conn.commit()
        
        session['user_email'] = email
        session['user_name'] = user['name']
        session['user_id'] = user['id']
        
        return jsonify({
            "success": True,
            "redirect": url_for('home'),
            "user": {
                "name": user['name'],
                "email": user['email'],
                "join_date": user['created_at']
            }
        })
    except Exception as e:
        app.logger.error(f"Login error: {str(e)}")
        return jsonify({"success": False, "message": "An error occurred during login."}), 500
    finally:
        conn.close()

@app.route('/api/signup', methods=['POST'])
def signup_post():
    data = request.get_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not name or not email or not password:
        return jsonify({"success": False, "message": "All fields are required."}), 400

    if len(password) < 8:
        return jsonify({"success": False, "message": "Password must be at least 8 characters."}), 400

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (name, email, hashed_password)
        )
        user_id = cursor.lastrowid
        
        # Initialize user progress
        cursor.execute(
            "INSERT INTO user_progress (user_id, last_activity) VALUES (?, ?)",
            (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        conn.commit()
        
        session['user_email'] = email
        session['user_name'] = name
        session['user_id'] = user_id
        
        return jsonify({
            "success": True,
            "redirect": url_for('home'),
            "user": {
                "name": name,
                "email": email,
                "join_date": datetime.now().strftime("%Y-%m-%d")
            }
        })
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Email already exists."}), 409
    except Exception as e:
        app.logger.error(f"Signup error: {str(e)}")
        return jsonify({"success": False, "message": "An error occurred during signup."}), 500
    finally:
        conn.close()

# ======= Interview Routes =======
@app.route('/interview')
def interview_home():
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    
    try:
        conn = get_db_connection()
        careers = conn.execute('SELECT * FROM careers').fetchall()
        
        progress = conn.execute(
            "SELECT progress_data FROM user_progress WHERE user_id = ?", 
            (session['user_id'],)
        ).fetchone()
        
        progress_data = progress['progress_data'] if progress else None
        
        return render_template('interview.html', 
                            careers=careers,
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'),
                            progress=progress_data)
        
    except Exception as e:
        app.logger.error(f"Interview home error: {str(e)}")
        return render_template('error.html', 
                            message="Error loading interview page",
                            user_email=session.get('user_email'))
    finally:
        conn.close()

@app.route('/start_interview', methods=['POST'])
def start_interview():
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    career_id = data.get('career_id')
    difficulty = data.get('difficulty', 'beginner')
    
    try:
        conn = get_db_connection()
        
        # Get questions for selected career and difficulty
        questions = conn.execute(
            """SELECT id, question, question_type 
               FROM interview_questions 
               WHERE career_id = ? AND difficulty_level = ? 
               ORDER BY RANDOM() LIMIT 7""",
            (career_id, difficulty)
        ).fetchall()
        
        if not questions:
            return jsonify({'error': 'No questions available'}), 404
        
        questions = [dict(q) for q in questions]
        
        # Create interview session
        cur = conn.execute(
            """INSERT INTO interviews 
               (user_id, career_id, difficulty, start_time) 
               VALUES (?, ?, ?, ?)""",
            (session['user_id'], career_id, difficulty, datetime.utcnow())
        )
        interview_id = cur.lastrowid
        
        # Save questions for this session
        for q in questions:
            conn.execute(
                """INSERT INTO interview_questions_mapping 
                   (interview_id, question_id) VALUES (?, ?)""",
                (interview_id, q['id'])
            )
        
        conn.commit()
        
        # Store current interview in session
        session['current_interview'] = {
            'id': interview_id,
            'career_id': career_id,
            'current_question': 0,
            'questions': questions,
            'answers': [],
            'difficulty': difficulty
        }
        
        return jsonify({
            'interview_id': interview_id,
            'first_question': questions[0],
            'total_questions': len(questions)
        })
        
    except Exception as e:
        app.logger.error(f"Interview start error: {str(e)}")
        return jsonify({'error': 'Failed to start interview'}), 500
    finally:
        conn.close()

@app.route('/submit_answer', methods=['POST'])
def submit_answer():
    if not session.get('current_interview'):
        return jsonify({'error': 'No active interview'}), 400
    
    data = request.json
    answer_text = data.get('answer', '').strip()
    is_audio = data.get('is_audio', False)
    
    # Validate answer is provided
    if not answer_text and not is_audio:
        return jsonify({'error': 'Please provide an answer before continuing'}), 400
    
    try:
        interview = session['current_interview']
        current_q_index = interview['current_question']
        current_q = interview['questions'][current_q_index]
        
        # Store answer in session
        interview['answers'].append({
            'question_id': current_q['id'],
            'text': answer_text,
            'is_audio': is_audio,
            'timestamp': datetime.utcnow().isoformat(),
            'answered': True  # Track if question was answered
        })
        
        # Check if interview complete
        if current_q_index >= len(interview['questions']) - 1:
            return finish_interview(interview)
            
        # Move to next question
        next_q_index = current_q_index + 1
        interview['current_question'] = next_q_index
        session['current_interview'] = interview
        session.modified = True
        
        return jsonify({
            'next_question': interview['questions'][next_q_index],
            'progress': f"{next_q_index + 1}/{len(interview['questions'])}"
        })
        
    except Exception as e:
        app.logger.error(f"Answer submission error: {str(e)}")
        return jsonify({'error': 'Failed to process answer'}), 500

def finish_interview(interview):
    try:
        conn = get_db_connection()
        
        # Save all answers to database
        for answer in interview['answers']:
            conn.execute(
                """INSERT INTO interview_answers 
                   (interview_id, question_id, answer_text, is_audio, timestamp, answered) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (interview['id'], answer['question_id'], 
                 answer['text'], answer['is_audio'], answer['timestamp'],
                 answer.get('answered', False))
            )
        
        # Generate analysis only for answered questions
        answered_questions = [a for a in interview['answers'] if a.get('answered')]
        if not answered_questions:
            return jsonify({
                'status': 'completed',
                'results': {
                    'score': 0,
                    'feedback': "You didn't answer any questions. Please try again.",
                    'strengths': "None",
                    'areas_to_improve': "Answer all questions",
                    'technical_score': 0,
                    'communication_score': 0,
                    'confidence_score': 0
                }
            })
        
        analysis = analyze_answers(answered_questions)
        
        # Update interview completion
        conn.execute(
            """UPDATE interviews 
               SET end_time = ?, overall_score = ? 
               WHERE id = ?""",
            (datetime.utcnow(), analysis.get('overall_score'), interview['id'])
        )
        
        conn.commit()
        
        return jsonify({
            'status': 'completed',
            'results': {
                'score': analysis.get('overall_score', 0),
                'feedback': analysis.get('feedback'),
                'strengths': analysis.get('strengths'),
                'areas_to_improve': analysis.get('areas_to_improve'),
                'technical_score': analysis.get('technical_score'),
                'communication_score': analysis.get('communication_score'),
                'confidence_score': analysis.get('confidence_score')
            }
        })
        
    except Exception as e:
        app.logger.error(f"Interview completion error: {str(e)}")
        return jsonify({'error': 'Failed to complete interview'}), 500
    finally:
        conn.close()

def analyze_answers(answers):
    """Analyze only answered questions"""
    if not answers:
        return {
            'overall_score': 0,
            'technical_score': 0,
            'communication_score': 0,
            'confidence_score': 0,
            'feedback': "No answers provided",
            'strengths': "None",
            'areas_to_improve': "Please attempt all questions"
        }
    
    # Calculate scores only for answered questions
    total_score = 0
    tech_score = 0
    comm_score = 0
    
    for answer in answers:
        if not answer.get('text'):
            continue
            
        length_score = min(len(answer['text']) / 20, 1) * 20
        keyword_score = 10 if any(kw in answer['text'].lower() 
                          for kw in ['experience', 'project', 'learn']) else 5
        total_score += length_score + keyword_score
        
        tech_score += length_score * 1.2
        
        structure_bonus = 5 if ('first' in answer['text'] and 
                              'then' in answer['text']) else 0
        comm_score += length_score * 0.8 + structure_bonus
    
    # Normalize scores
    total_score = min(int(total_score / len(answers)), 100)
    tech_score = min(int(tech_score / len(answers)), 100)
    comm_score = min(int(comm_score / len(answers)), 100)
    confidence_score = min(total_score + 10, 100)
    
    return {
        'overall_score': total_score,
        'technical_score': tech_score,
        'communication_score': comm_score,
        'confidence_score': confidence_score,
        'feedback': "You demonstrated good knowledge but could improve your answer structure.",
        'strengths': "Technical understanding, clear communication",
        'areas_to_improve': "Answer structure, providing more specific examples"
    }

# ======= Test Routes =======
@app.route('/test/select')
def test_selection():
    if 'user_email' not in session:
        return redirect(url_for('register_page'))
    
    try:
        conn = get_db_connection()
        subjects = conn.execute('''
            SELECT DISTINCT c.name FROM careers c
            JOIN interview_questions iq ON c.id = iq.career_id
        ''').fetchall()
        
        return render_template('test_selection.html',
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'),
                            subjects=[s['name'] for s in subjects])
    except Exception as e:
        app.logger.error(f"Test selection error: {str(e)}")
        return render_template('error.html',
                            message="Error loading test selection",
                            user_email=session.get('user_email'))
    finally:
        conn.close()

@app.route('/test/start', methods=['POST'])
def test_start():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    subject = data.get('subject')
    topic = data.get('topic')
    
    try:
        conn = get_db_connection()
        
        # Create test session
        cursor = conn.execute('''
            INSERT INTO test_sessions 
            (user_id, subject, topic, start_time, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            session['user_id'],
            subject,
            topic,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'in_progress'
        ))
        test_session_id = cursor.lastrowid
        
        # Get questions
        questions = conn.execute('''
            SELECT iq.id, iq.question, iq.question_type, iq.difficulty_level
            FROM interview_questions iq
            JOIN careers c ON iq.career_id = c.id
            WHERE c.name = ? AND iq.difficulty_level = ?
            ORDER BY RANDOM() LIMIT 10
        ''', (subject, 'beginner')).fetchall()
        
        # Add questions to test
        for i, question in enumerate(questions, 1):
            conn.execute('''
                INSERT INTO test_questions
                (test_session_id, question_id, question_order)
                VALUES (?, ?, ?)
            ''', (test_session_id, question['id'], i))
        
        conn.commit()
        
        # Store in session
        session['current_test'] = {
            'id': test_session_id,
            'subject': subject,
            'topic': topic,
            'questions': [dict(q) for q in questions]
        }
        
        return jsonify({
            'success': True,
            'redirect': url_for('test_questions')
        })
    except Exception as e:
        app.logger.error(f"Test start error: {str(e)}")
        return jsonify({'error': 'Failed to start test'}), 500
    finally:
        conn.close()

@app.route('/test/questions')
def test_questions():
    if 'user_id' not in session or 'current_test' not in session:
        return redirect(url_for('register_page'))
    
    try:
        conn = get_db_connection()
        questions = conn.execute('''
            SELECT iq.* FROM test_questions tq
            JOIN interview_questions iq ON tq.question_id = iq.id
            WHERE tq.test_session_id = ?
            ORDER BY tq.question_order
        ''', (session['current_test']['id'],)).fetchall()
        
        session['current_test']['questions'] = [dict(q) for q in questions]
        session.modified = True
        
        return render_template('test_questions.html',
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'),
                            test_session=session['current_test'])
    except Exception as e:
        app.logger.error(f"Test questions error: {str(e)}")
        return render_template('error.html',
                            message="Error loading test questions",
                            user_email=session.get('user_email'))
    finally:
        conn.close()

@app.route('/test/submit-answer', methods=['POST'])
def test_submit_answer():
    if 'user_id' not in session or 'current_test' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    question_id = data.get('question_id')
    answer = data.get('answer')
    is_correct = data.get('is_correct')
    
    try:
        conn = get_db_connection()
        
        conn.execute('''
            INSERT INTO test_answers
            (test_session_id, question_id, user_id, answer, is_correct, answered_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            session['current_test']['id'],
            question_id,
            session['user_id'],
            answer,
            is_correct,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Answer submission error: {str(e)}")
        return jsonify({'error': 'Failed to submit answer'}), 500
    finally:
        conn.close()

@app.route('/test/complete', methods=['POST'])
def test_complete():
    if 'user_id' not in session or 'current_test' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        
        # Calculate score
        result = conn.execute('''
            SELECT COUNT(*) as correct_answers FROM test_answers
            WHERE test_session_id = ? AND is_correct = 1
        ''', (session['current_test']['id'],)).fetchone()
        
        score = result['correct_answers'] if result else 0
        
        # Update test session
        conn.execute('''
            UPDATE test_sessions
            SET end_time = ?, status = 'completed', score = ?
            WHERE id = ?
        ''', (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            score,
            session['current_test']['id']
        ))
        
        conn.commit()
        
        test_id = session['current_test']['id']
        session.pop('current_test', None)
        
        return jsonify({
            'success': True,
            'redirect': url_for('test_results', test_id=test_id)
        })
    except Exception as e:
        app.logger.error(f"Test completion error: {str(e)}")
        return jsonify({'error': 'Failed to complete test'}), 500
    finally:
        conn.close()

@app.route('/test/results/<int:test_id>')
def test_results(test_id):
    if 'user_id' not in session:
        return redirect(url_for('register_page'))
    
    try:
        conn = get_db_connection()
        
        test_session = conn.execute('''
            SELECT * FROM test_sessions
            WHERE id = ? AND user_id = ?
        ''', (test_id, session['user_id'])).fetchone()
        
        if not test_session:
            return render_template('error.html',
                                message="Test results not found",
                                user_email=session.get('user_email'))
        
        questions = conn.execute('''
            SELECT iq.question, ta.answer, ta.is_correct
            FROM test_answers ta
            JOIN interview_questions iq ON ta.question_id = iq.id
            WHERE ta.test_session_id = ?
            ORDER BY ta.id
        ''', (test_id,)).fetchall()
        
        return render_template('test_results.html',
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'),
                            test_session=dict(test_session),
                            questions=[dict(q) for q in questions])
    except Exception as e:
        app.logger.error(f"Test results error: {str(e)}")
        return render_template('error.html',
                            message="Error loading test results",
                            user_email=session.get('user_email'))
    finally:
        conn.close()

# ======= Static Page Routes =======
@app.route('/aboutus')
def about():
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    return render_template('aboutus.html', 
                         user_email=session.get('user_email'),
                         user_name=session.get('user_name'))

@app.route('/library')
def library():
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    try:
        return render_template('library.html', 
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'))
    except Exception as e:
        app.logger.error(f"Library error: {str(e)}")
        return render_template('error.html', 
                            message="Error loading library page",
                            user_email=session.get('user_email'))

@app.route('/services')
def services():
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    
    services_data = [
        {"name": "Career Counseling", "icon": "fa-graduation-cap"},
        {"name": "Resume Review", "icon": "fa-file-text"},
        {"name": "Mock Interviews", "icon": "fa-comments"}
    ]
    
    return render_template('services.html',
                         services=services_data,
                         user_email=session.get('user_email'),
                         user_name=session.get('user_name'))

@app.route('/profile')
def profile():
    if 'user_email' not in session:
        return redirect(url_for('register_page'))
    return render_template('profile.html')

@app.route('/contact')
def contact():
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    return render_template('contact.html',
                         user_email=session.get('user_email'),
                         user_name=session.get('user_name'))

@app.route('/resume')
def resume_builder():
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    
    try:
        return render_template('resume.html',
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'))
    except Exception as e:
        app.logger.error(f"Resume builder error: {str(e)}")
        return render_template('error.html',
                            message="Error loading resume builder",
                            user_email=session.get('user_email'))    

@app.route('/chatbot')
def career_chatbot():
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    
    try:
        return render_template('chatbot.html',
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'),
                            initial_messages=[])
    except Exception as e:
        app.logger.error(f"Chatbot error: {str(e)}")
        return render_template('error.html',
                            message="Error loading chatbot",
                            user_email=session.get('user_email'))  

@app.route('/jobs')
def job_listings():
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    
    try:
        conn = get_db_connection()
        jobs = conn.execute('''
            SELECT j.*, c.name as career_name 
            FROM jobs j
            LEFT JOIN careers c ON j.career_id = c.id
            ORDER BY j.posted_at DESC
        ''').fetchall()
        
        return render_template('jobs.html',
                            jobs=[dict(job) for job in jobs],
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'))
    except Exception as e:
        app.logger.error(f"Job listings error: {str(e)}")
        return render_template('error.html',
                            message="Error loading job listings",
                            user_email=session.get('user_email'))
    finally:
        conn.close()

@app.route('/jobs/<int:job_id>')
def job_details(job_id):
    if not session.get('user_email'):
        return redirect(url_for('register_page'))
    
    try:
        conn = get_db_connection()
        job = conn.execute('''
            SELECT j.*, c.name as career_name 
            FROM jobs j
            LEFT JOIN careers c ON j.career_id = c.id
            WHERE j.id = ?
        ''', (job_id,)).fetchone()
        
        if not job:
            return render_template('error.html',
                                message="Job not found",
                                user_email=session.get('user_email')), 404
        
        return render_template('job.html',
                            job=dict(job),
                            user_email=session.get('user_email'),
                            user_name=session.get('user_name'))
    except Exception as e:
        app.logger.error(f"Job details error: {str(e)}")
        return render_template('error.html',
                            message="Error loading job details",
                            user_email=session.get('user_email'))
    finally:
        conn.close()

@app.route('/apply', methods=['POST'])
def apply_for_job():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    job_id = data.get('job_id')
    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        
        # Verify job exists
        job = conn.execute('SELECT id FROM jobs WHERE id = ?', (job_id,)).fetchone()
        if not job:
            return jsonify({"error": "Job not found"}), 404
        
        # In a real app, you would:
        # 1. Create an applications table
        # 2. Store the application
        # 3. Send confirmation email
        
        return jsonify({
            "status": "success",
            "message": "Application submitted successfully",
            "job_id": job_id,
            "user_id": user_id
        })
    except Exception as e:
        app.logger.error(f"Job application error: {str(e)}")
        return jsonify({"error": "Failed to process application"}), 500
    finally:
        conn.close()
# ======= Error Handlers =======
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', 
                         message="Page not found",
                         user_email=session.get('user_email')), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', 
                         message="Internal server error",
                         user_email=session.get('user_email')), 500

@app.errorhandler(werkzeug.routing.BuildError)
def handle_build_error(e):
    app.logger.error(f"URL Build Error: {str(e)}")
    return redirect(url_for('register_page'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)