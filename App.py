import os
from datetime import datetime
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, 
    get_jwt_identity, decode_token
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit, join_room

# ============================================================================
# 1. APPLICATION & CONFIGURATION SETUP
# ============================================================================
app = Flask(__name__)
app.url_map.strict_slashes = False

# Enable Cross-Origin Resource Sharing
CORS(app)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fudma_pm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# JWT Configuration
app.config['JWT_SECRET_KEY'] = 'fudma-codespaces-dev-secret-key-2024'
app.config['JWT_HEADER_TYPE'] = 'Token'  # Matches the frontend "Token <hash>" expectation
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False # Prevents expiration during development

# File Upload Configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'media', 'documents')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ============================================================================
# 2. DATABASE MODELS
# ============================================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    
    # System Clearance / Role (student, supervisor, coordinator, admin)
    role = db.Column(db.String(20), default='student')
    
    # Personal Identity
    first_name = db.Column(db.String(50), default='')
    last_name = db.Column(db.String(50), default='')
    matric_number = db.Column(db.String(20), unique=True, nullable=True)
    department = db.Column(db.String(100), default='Computer Science')
    phone = db.Column(db.String(20), default='')
    bio = db.Column(db.Text, default='')
    
    # Academic State
    level = db.Column(db.String(10), default='')
    session = db.Column(db.String(20), default='')
    date_joined = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password): 
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password): 
        return check_password_hash(self.password_hash, password)
        
    @property
    def full_name(self): 
        return f"{self.first_name} {self.last_name}".strip() or self.username
        
    @property
    def avatar_initials(self):
        fn = self.first_name[:1] if self.first_name else ''
        ln = self.last_name[:1] if self.last_name else ''
        return (fn + ln).upper() or self.username[:2].upper()

    def to_dict(self):
        return {
            'id': self.id, 
            'username': self.username, 
            'email': self.email, 
            'role': self.role,
            'first_name': self.first_name, 
            'last_name': self.last_name, 
            'full_name': self.full_name,
            'matric_number': self.matric_number, 
            'department': self.department, 
            'phone': self.phone,
            'bio': self.bio, 
            'avatar_initials': self.avatar_initials, 
            'level': self.level,
            'session': self.session, 
            'date_joined': self.date_joined.isoformat()
        }

class Topic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, default='')
    suggested_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self): 
        return {
            'id': self.id, 
            'title': self.title, 
            'description': self.description, 
            'is_available': self.is_available, 
            'created_at': self.created_at.isoformat()
        }

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    abstract = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='proposal')
    session = db.Column(db.String(20), default='2023/2024')
    
    # Relationships (Foreign Keys)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'), nullable=True)
    
    deadline = db.Column(db.String(20), nullable=True)
    
    # Standardized Grading Rubric
    rubric_code = db.Column(db.Float, default=0.0)         # Scored out of 40
    rubric_docs = db.Column(db.Float, default=0.0)         # Scored out of 30
    rubric_presentation = db.Column(db.Float, default=0.0) # Scored out of 30
    
    keywords = db.Column(db.String(255), default='')
    tools_used = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Cascading Sub-resources
    student = db.relationship('User', foreign_keys=[student_id])
    supervisor = db.relationship('User', foreign_keys=[supervisor_id])
    milestones = db.relationship('Milestone', backref='project', lazy=True, cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='project', lazy=True, cascade="all, delete-orphan")
    documents = db.relationship('Document', backref='project', lazy=True, cascade="all, delete-orphan")

    @property
    def total_score(self):
        return round(self.rubric_code + self.rubric_docs + self.rubric_presentation, 1)
        
    @property
    def grade_letter(self):
        score = self.total_score
        if score == 0: return ""
        if score >= 70: return "A"
        if score >= 60: return "B"
        if score >= 50: return "C"
        if score >= 45: return "D"
        return "F"

    def to_dict(self, detail=False):
        milestones_done = len([m for m in self.milestones if m.status == 'completed'])
        total_milestones = len(self.milestones)
        
        data = {
            'id': self.id, 
            'title': self.title, 
            'status': self.status, 
            'session': self.session,
            'student_name': self.student.full_name, 
            'student_matric': self.student.matric_number,
            'student_avatar': self.student.avatar_initials, 
            'supervisor_name': self.supervisor.full_name if self.supervisor else None,
            'created_at': self.created_at.isoformat(), 
            'updated_at': self.updated_at.isoformat(),
            'deadline': self.deadline, 
            'total_score': self.total_score, 
            'grade_letter': self.grade_letter, 
            'keywords': self.keywords, 
            'tools_used': self.tools_used,
            'milestone_count': total_milestones, 
            'completed_milestones': milestones_done,
            'progress_percent': round((milestones_done / total_milestones * 100)) if total_milestones else 0
        }
        
        # Inject heavier cascading data only when viewing a specific project
        if detail:
            data.update({
                'abstract': self.abstract, 
                'student': self.student.to_dict(),
                'supervisor': self.supervisor.to_dict() if self.supervisor else None,
                'rubric_code': self.rubric_code, 
                'rubric_docs': self.rubric_docs, 
                'rubric_presentation': self.rubric_presentation,
                'milestones': [m.to_dict() for m in self.milestones], 
                'comments': [c.to_dict() for c in self.comments],
                'documents': [d.to_dict() for d in self.documents]
            })
        return data

class Milestone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    due_date = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(20), default='pending')
    
    def to_dict(self): 
        return {
            'id': self.id, 
            'title': self.title, 
            'description': self.description, 
            'due_date': self.due_date, 
            'status': self.status
        }

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_feedback = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    author = db.relationship('User')
    
    def to_dict(self): 
        return {
            'id': self.id, 
            'content': self.content, 
            'is_feedback': self.is_feedback, 
            'created_at': self.created_at.isoformat(), 
            'author_name': self.author.full_name, 
            'author_role': self.author.role, 
            'author_initials': self.author.avatar_initials
        }

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    doc_type = db.Column(db.String(50), default='other')
    file_path = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    uploaded_by = db.relationship('User')
    
    def to_dict(self): 
        return {
            'id': self.id, 
            'title': self.title, 
            'doc_type': self.doc_type, 
            'file_size': self.file_size, 
            'uploaded_at': self.uploaded_at.isoformat(), 
            'uploaded_by_name': self.uploaded_by.full_name, 
            'file_url': f'/media/documents/{self.file_path}'
        }

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    target_role = db.Column(db.String(20), default='')
    is_pinned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    author = db.relationship('User')
    
    def to_dict(self): 
        return {
            'id': self.id, 
            'title': self.title, 
            'body': self.body, 
            'target_role': self.target_role, 
            'is_pinned': self.is_pinned, 
            'created_at': self.created_at.isoformat(), 
            'author_name': self.author.full_name
        }

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notif_type = db.Column(db.String(50), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self): 
        return {
            'id': self.id, 
            'title': self.title, 
            'message': self.message, 
            'notif_type': self.notif_type, 
            'is_read': self.is_read, 
            'created_at': self.created_at.isoformat()
        }


# ============================================================================
# 3. WEBSOCKETS & EVENT EMITTERS
# ============================================================================

def get_current_user(): 
    return User.query.get(int(get_jwt_identity()))

def send_notification(recipient_id, title, message, notif_type='info'):
    """Helper function to log a notification and emit it via WebSocket."""
    n = Notification(recipient_id=recipient_id, title=title, message=message, notif_type=notif_type)
    db.session.add(n)
    db.session.commit()
    socketio.emit('new_notification', n.to_dict(), room=f"user_{recipient_id}")

@socketio.on('authenticate')
def handle_authenticate(data):
    """Binds a connected WebSocket client to their specific user ID room."""
    token = data.get('token')
    if token:
        try:
            decoded = decode_token(token)
            join_room(f"user_{decoded['sub']}")
        except: 
            pass


# ============================================================================
# 4. REST API ROUTES
# ============================================================================

# --- AUTHENTICATION & USER MANAGEMENT ---

@app.route('/api/auth/register/', methods=['POST'])
def register():
    data = request.get_json()
    if User.query.filter_by(username=data.get('username')).first(): 
        return jsonify({'message': 'Username already exists'}), 400
        
    u = User(
        username=data['username'], 
        email=data['email'], 
        role=data.get('role', 'student'), 
        first_name=data.get('first_name', ''), 
        last_name=data.get('last_name', ''), 
        matric_number=data.get('matric_number'), 
        level=data.get('level',''), 
        session=data.get('session','')
    )
    u.set_password(data['password'])
    db.session.add(u)
    db.session.commit()
    
    return jsonify({'token': create_access_token(identity=str(u.id)), 'user': u.to_dict()}), 201

@app.route('/api/auth/login/', methods=['POST'])
def login():
    data = request.get_json()
    u = User.query.filter_by(username=data.get('username')).first()
    
    if u and u.check_password(data.get('password')):
        return jsonify({'token': create_access_token(identity=str(u.id)), 'user': u.to_dict()}), 200
        
    return jsonify({'message': 'Invalid credentials'}), 401

@app.route('/api/auth/logout/', methods=['POST'])
@jwt_required()
def logout(): 
    return jsonify({'message': 'Logged out successfully'})

@app.route('/api/auth/profile/', methods=['GET', 'PATCH'])
@jwt_required()
def profile():
    u = get_current_user()
    if request.method == 'PATCH':
        for key in ['first_name', 'last_name', 'email', 'phone', 'bio']:
            if key in request.json: 
                setattr(u, key, request.json[key])
        db.session.commit()
    return jsonify(u.to_dict())

@app.route('/api/auth/users/', methods=['GET'])
@jwt_required()
def users():
    query = User.query
    
    if request.args.get('role'): 
        query = query.filter_by(role=request.args.get('role'))
        
    search = request.args.get('search', '').lower()
    if search:
        query = query.filter(
            (User.first_name.ilike(f'%{search}%')) | 
            (User.last_name.ilike(f'%{search}%')) | 
            (User.matric_number.ilike(f'%{search}%'))
        )
    
    # Server-Side Pagination implementation
    page = request.args.get('page', 1, type=int)
    pagination = query.paginate(page=page, per_page=12, error_out=False)
    
    return jsonify({
        'results': [u.to_dict() for u in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })

# --- DASHBOARD & ANALYTICS ---

@app.route('/api/dashboard/', methods=['GET'])
@jwt_required()
def dashboard():
    u = get_current_user()
    res = {
        'announcements': [a.to_dict() for a in Announcement.query.order_by(Announcement.created_at.desc()).limit(3)],
        'notifications': [n.to_dict() for n in Notification.query.filter_by(recipient_id=u.id).order_by(Notification.created_at.desc()).limit(5)]
    }
    
    if u.role == 'student':
        p = Project.query.filter_by(student_id=u.id).first()
        if p:
            res['project'] = p.to_dict(detail=True)
            res['milestones'] = [m.to_dict() for m in p.milestones]
            
    elif u.role == 'supervisor':
        projs = Project.query.filter_by(supervisor_id=u.id).all()
        res['supervised_projects'] = [p.to_dict() for p in projs]
        res['recent_projects'] = res['supervised_projects'][:5]
        
    else: # Admin & Coordinator
        res['total_projects'] = Project.query.count()
        res['total_students'] = User.query.filter_by(role='student').count()
        res['recent_projects'] = [p.to_dict() for p in Project.query.order_by(Project.created_at.desc()).limit(5)]
        
        status_counts = db.session.query(Project.status, db.func.count(Project.id)).group_by(Project.status).all()
        res['by_status'] = {s: count for s, count in status_counts}
        
    return jsonify(res)

@app.route('/api/stats/', methods=['GET'])
@jwt_required()
def stats():
    status_counts = db.session.query(Project.status, db.func.count(Project.id)).group_by(Project.status).all()
    sessions_raw = db.session.query(Project.session).distinct().all()
    
    return jsonify({
        'total': Project.query.count(),
        'total_students': User.query.filter_by(role='student').count(),
        'total_supervisors': User.query.filter_by(role='supervisor').count(),
        'by_status': {s: {'count': c, 'label': s.replace('_', ' ').title()} for s, c in status_counts},
        'sessions': [r[0] for r in sessions_raw if r[0]]
    })

# --- PROJECT MANAGEMENT ---

@app.route('/api/projects/', methods=['GET', 'POST'])
@jwt_required()
def projects():
    u = get_current_user()
    
    if request.method == 'GET':
        query = Project.query
        
        # Role-based visibility
        if u.role == 'student': 
            query = query.filter_by(student_id=u.id)
        elif u.role == 'supervisor': 
            query = query.filter_by(supervisor_id=u.id)

        if request.args.get('status'): 
            query = query.filter_by(status=request.args.get('status'))
            
        search = request.args.get('search', '').lower()
        if search:
            query = query.join(User, Project.student_id == User.id).filter(
                (Project.title.ilike(f'%{search}%')) | 
                (User.first_name.ilike(f'%{search}%')) | 
                (User.last_name.ilike(f'%{search}%')) | 
                (User.matric_number.ilike(f'%{search}%'))
            )
        
        # Server-Side Pagination
        page = request.args.get('page', 1, type=int)
        pagination = query.order_by(Project.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
        
        return jsonify({
            'results': [p.to_dict() for p in pagination.items],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })

    if request.method == 'POST':
        data = request.get_json()
        p = Project(
            title=data['title'], 
            abstract=data.get('abstract',''), 
            session=data.get('session','2023/2024'),
            keywords=data.get('keywords',''), 
            tools_used=data.get('tools_used',''),
            topic_id=data.get('topic_id') or None, 
            supervisor_id=data.get('supervisor_id') or None,
            student_id=u.id if u.role == 'student' else data.get('student_id', u.id)
        )
        
        if p.topic_id: 
            Topic.query.get(p.topic_id).is_available = False
            
        db.session.add(p)
        db.session.commit()
        return jsonify(p.to_dict()), 201

@app.route('/api/projects/<int:p_id>/', methods=['GET', 'PATCH'])
@jwt_required()
def project_detail(p_id):
    p = Project.query.get_or_404(p_id)
    
    if request.method == 'PATCH':
        data = request.get_json()
        
        # Process State Mutation
        if 'status' in data: p.status = data['status']
        
        # Process Grading Rubric Update
        if 'rubric_code' in data: p.rubric_code = float(data['rubric_code'])
        if 'rubric_docs' in data: p.rubric_docs = float(data['rubric_docs'])
        if 'rubric_presentation' in data: p.rubric_presentation = float(data['rubric_presentation'])
        
        db.session.commit()
        
        # Real-time WebSocket Notification on Grade Update
        if any(k in data for k in ['rubric_code', 'rubric_docs', 'rubric_presentation']):
            send_notification(
                recipient_id=p.student_id, 
                title="Project Graded", 
                message=f"Your project '{p.title}' has received updated rubric scores.", 
                notif_type="success"
            )
            
    return jsonify(p.to_dict(detail=True))

# --- SUB-RESOURCES (Milestones, Comments, Documents) ---

@app.route('/api/projects/<int:p_id>/milestones/', methods=['POST'])
@jwt_required()
def add_milestone(p_id):
    data = request.get_json()
    m = Milestone(
        project_id=p_id, 
        title=data['title'], 
        description=data.get('description',''), 
        due_date=data.get('due_date',''), 
        status=data.get('status','pending')
    )
    db.session.add(m)
    db.session.commit()
    return jsonify(m.to_dict()), 201

@app.route('/api/projects/<int:p_id>/milestones/<int:m_id>/', methods=['PATCH'])
@jwt_required()
def update_milestone(p_id, m_id):
    m = Milestone.query.get_or_404(m_id)
    m.status = request.json.get('status', m.status)
    db.session.commit()
    return jsonify(m.to_dict())

@app.route('/api/projects/<int:p_id>/comments/', methods=['POST'])
@jwt_required()
def add_comment(p_id):
    u = get_current_user()
    p = Project.query.get_or_404(p_id)
    c = Comment(
        project_id=p_id, 
        author_id=u.id, 
        content=request.json['content'], 
        is_feedback=request.json.get('is_feedback', False)
    )
    db.session.add(c)
    db.session.commit()
    
    # Real-time notification for comments
    recipient_id = p.student_id if u.role == 'supervisor' else p.supervisor_id
    if recipient_id:
        send_notification(
            recipient_id=recipient_id, 
            title="New Comment", 
            message=f"{u.first_name} commented on '{p.title}'", 
            notif_type="info"
        )

    return jsonify(c.to_dict()), 201

@app.route('/api/projects/<int:p_id>/documents/', methods=['POST'])
@jwt_required()
def upload_doc(p_id):
    if 'file' not in request.files: 
        return jsonify({"error": "No file provided"}), 400
        
    f = request.files['file']
    filename = secure_filename(f"{int(datetime.utcnow().timestamp())}_{f.filename}")
    f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    d = Document(
        project_id=p_id, 
        uploaded_by_id=get_jwt_identity(), 
        title=request.form.get('title', f.filename), 
        doc_type=request.form.get('doc_type', 'other'), 
        file_path=filename, 
        file_size=os.path.getsize(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    )
    db.session.add(d)
    db.session.commit()
    return jsonify(d.to_dict()), 201

# --- TOPICS & ANNOUNCEMENTS ---

@app.route('/api/topics/', methods=['GET', 'POST'])
@jwt_required()
def topics():
    if request.method == 'POST':
        t = Topic(
            title=request.json['title'], 
            description=request.json.get('description',''), 
            suggested_by_id=get_jwt_identity()
        )
        db.session.add(t)
        db.session.commit()
        return jsonify(t.to_dict()), 201
        
    return jsonify([t.to_dict() for t in Topic.query.all()])

@app.route('/api/announcements/', methods=['GET', 'POST'])
@jwt_required()
def announcements():
    if request.method == 'POST':
        a = Announcement(
            author_id=get_jwt_identity(), 
            title=request.json['title'], 
            body=request.json['body'], 
            target_role=request.json.get('target_role',''), 
            is_pinned=request.json.get('is_pinned',False)
        )
        db.session.add(a)
        db.session.commit()
        
        # Broadcast announcement to all connected WebSocket clients
        socketio.emit('new_notification', {
            'id': 0, 
            'title': 'New Announcement', 
            'message': a.title, 
            'notif_type': 'info', 
            'is_read': False, 
            'created_at': a.created_at.isoformat()
        })
        
        return jsonify(a.to_dict()), 201
        
    return jsonify([a.to_dict() for a in Announcement.query.order_by(Announcement.created_at.desc()).all()])

# --- NOTIFICATIONS & MEDIA ---

@app.route('/api/notifications/', methods=['GET'])
@jwt_required()
def get_notifs(): 
    notifs = Notification.query.filter_by(recipient_id=get_jwt_identity()).order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([n.to_dict() for n in notifs])

@app.route('/api/notifications/read/', methods=['POST'])
@jwt_required()
def read_notifs():
    Notification.query.filter_by(recipient_id=get_jwt_identity(), is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({"message": "Marked read"}), 200

@app.route('/media/documents/<path:filename>')
def serve_media(filename): 
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- SPA FALLBACK ROUTE ---
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    if not path.startswith('api/') and not path.startswith('media/'):
        try: 
            return send_file('index.html')
        except: 
            return "index.html not found in root directory.", 404
    return jsonify({"error": "Endpoint not found"}), 404

# ============================================================================
# 5. DATABASE INITIALIZATION & SEEDING
# ============================================================================

def init_db():
    """Drops and rebuilds the SQLite database with mock data for testing."""
    db.drop_all()
    db.create_all()
    
    print("🌱 Seeding Database with Users, Projects, and Grading Rubrics...")
    
    admin = User(username='admin', email='admin@fudma.edu.ng', role='admin', first_name='System', last_name='Admin')
    admin.set_password('admin123')
    
    coord = User(username='coordinator', email='coord@fudma.edu.ng', role='coordinator', first_name='Project', last_name='Coordinator')
    coord.set_password('coord123')
    
    superv = User(username='dr_ibrahim', email='ibrahim@fudma.edu.ng', role='supervisor', first_name='Dr. Ibrahim', last_name='Musa')
    superv.set_password('super123')
    
    users_to_add = [admin, coord, superv]
    
    # Generate 25 mock students for Pagination testing
    for i in range(1, 26):
        s = User(
            username=f'student_{i}', 
            email=f'student{i}@fudma.edu.ng', 
            role='student', 
            first_name='Student', 
            last_name=str(i), 
            matric_number=f'CS/23/10{i:02d}', 
            level='400L', 
            session='2023/2024'
        )
        s.set_password('student123')
        # We'll map 'ali_musa' to student_1 for consistency with previous login credentials
        if i == 1:
            s.username = 'ali_musa'
            s.first_name = 'Ali'
            s.last_name = 'Musa'
            s.matric_number = 'CS/23/1234'
            
        users_to_add.append(s)
        
    db.session.add_all(users_to_add)
    db.session.commit()

    student_1 = users_to_add[3] 

    t = Topic(title="AI Student Performance Predictor", description="ML model for predicting grades.", suggested_by_id=superv.id, is_available=False)
    db.session.add(t)
    db.session.commit()

    # Generate 15 mock projects for Pagination testing
    for i in range(1, 16):
        p = Project(
            title=f"Mock Project Analysis {i}" if i > 1 else "Smart Campus Mobile App", 
            status='in_progress', 
            student_id=users_to_add[2+i].id, 
            supervisor_id=superv.id, 
            topic_id=t.id if i == 1 else None,
            keywords="Mobile, React Native" if i == 1 else "Testing, Data",
            # Seed some projects with Rubric grades
            rubric_code=35.0 if i % 2 == 0 else 0.0, 
            rubric_docs=25.0 if i % 2 == 0 else 0.0, 
            rubric_presentation=20.0 if i % 2 == 0 else 0.0
        )
        db.session.add(p)

    db.session.commit()

    # Add initial milestones and interactions to the primary test project
    primary_project = Project.query.first()
    db.session.add_all([
        Milestone(project_id=primary_project.id, title="Requirement Gathering", status='completed'),
        Milestone(project_id=primary_project.id, title="UI/UX Design", status='completed'),
        Milestone(project_id=primary_project.id, title="Backend API", status='in_progress')
    ])
    
    db.session.add(Announcement(author_id=admin.id, title="Welcome to the Portal", body="Project registration for 2023/2024 is now open.", is_pinned=True))
    db.session.add(Notification(recipient_id=student_1.id, title="Project Assigned", message="Dr. Ibrahim is your assigned supervisor.", notif_type="info"))
    db.session.add(Comment(project_id=primary_project.id, author_id=superv.id, content="Good progress on the initial system designs.", is_feedback=True))
    
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        init_db()
    print("🚀 FUDMA CS Project Management Unit — Flask WebSockets & REST Engine")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
