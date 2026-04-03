import os
import django
from django.conf import settings
from django.urls import path, re_path
from django.http import HttpResponse
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.shortcuts import get_object_or_404
from django.core.files.base import ContentFile
from django.contrib import admin
from rest_framework import generics, status, serializers as drf_serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.parsers import MultiPartParser, FormParser

# ====================== DJANGO SETTINGS ======================
if not settings.configured:
    settings.configure(
        DEBUG=os.getenv('DEBUG', 'True') == 'True',
        SECRET_KEY=os.getenv('DJANGO_SECRET_KEY', 'fudma-codespaces-dev-secret-key-2024-change-in-production'),
        ROOT_URLCONF=__name__,
        INSTALLED_APPS=[
            'django.contrib.admin',
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
            'rest_framework',
            'corsheaders',
        ],
        MIDDLEWARE=[
            'corsheaders.middleware.CorsMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'db.sqlite3'}},
        USE_TZ=True,
        TIME_ZONE='Africa/Lagos',
        CORS_ALLOW_ALL_ORIGINS=True,
        REST_FRAMEWORK={
            'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.TokenAuthentication'],
            'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
        },
        MEDIA_ROOT='media',
        MEDIA_URL='/media/',
        STATIC_URL='/static/',
        AUTH_USER_MODEL='__main__.User',
        ALLOWED_HOSTS=['*'],
    )

django.setup()

# ====================== MODELS ======================
class User(AbstractUser):
    ROLE_CHOICES = [('student', 'Student'), ('supervisor', 'Supervisor'), ('coordinator', 'Project Coordinator'), ('admin', 'Admin')]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    matric_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    phone = models.CharField(max_length=15, blank=True)
    department = models.CharField(max_length=100, default='Computer Science')
    bio = models.TextField(blank=True)
    avatar_initials = models.CharField(max_length=3, blank=True)
    level = models.CharField(max_length=10, blank=True)
    session = models.CharField(max_length=20, blank=True)

    def save(self, *args, **kwargs):
        if not self.avatar_initials:
            fn = self.first_name[:1] if self.first_name else ''
            ln = self.last_name[:1] if self.last_name else ''
            self.avatar_initials = (fn + ln).upper() or self.username[:2].upper()
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.get_full_name() or self.username} ({self.role})"


class Topic(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    suggested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Project(models.Model):
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=20, default='proposal', choices=[('proposal','Proposal'),('approved','Approved'),('in_progress','In Progress'),('submitted','Submitted'),('revision','Revision'),('completed','Completed'),('rejected','Rejected')])
    session = models.CharField(max_length=20, default='2023/2024')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='student_projects')
    supervisor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supervised_projects')
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    grade = models.CharField(max_length=10, blank=True)
    score = models.FloatField(null=True, blank=True)
    keywords = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Milestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default='pending', choices=[('pending','Pending'),('completed','Completed')])

class Comment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class Document(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='documents')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/')
    file_size = models.PositiveIntegerField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    notif_type = models.CharField(max_length=50, blank=True)

class Announcement(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    body = models.TextField()
    target_role = models.CharField(max_length=20, blank=True, null=True)
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

# ====================== SERIALIZERS (your exact code) ======================
class UserSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id','username','email','first_name','last_name','role','matric_number','phone','department','bio','avatar_initials','level','session','date_joined']
        read_only_fields = ['id','avatar_initials','date_joined']

class RegisterSerializer(drf_serializers.ModelSerializer):
    password = drf_serializers.CharField(write_only=True)
    class Meta:
        model = User
        fields = ['username','email','password','first_name','last_name','role','matric_number','level','session']
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class LoginSerializer(drf_serializers.Serializer):
    username = drf_serializers.CharField()
    password = drf_serializers.CharField()
    def validate(self, data):
        user = authenticate(username=data['username'], password=data['password'])
        if not user: raise drf_serializers.ValidationError("Invalid credentials")
        data['user'] = user
        return data

class TopicSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = '__all__'
        read_only_fields = ['suggested_by','created_at']

class MilestoneSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = '__all__'
        read_only_fields = ['project']

class CommentSerializer(drf_serializers.ModelSerializer):
    author_name = drf_serializers.SerializerMethodField()
    author_role = drf_serializers.SerializerMethodField()
    author_initials = drf_serializers.SerializerMethodField()
    class Meta:
        model = Comment
        fields = '__all__'
        read_only_fields = ['author','created_at']
    def get_author_name(self, obj): return obj.author.get_full_name() or obj.author.username
    def get_author_role(self, obj): return obj.author.role
    def get_author_initials(self, obj): return obj.author.avatar_initials

class DocumentSerializer(drf_serializers.ModelSerializer):
    uploaded_by_name = drf_serializers.SerializerMethodField()
    file_url = drf_serializers.SerializerMethodField()
    class Meta:
        model = Document
        fields = '__all__'
        read_only_fields = ['uploaded_by','uploaded_at','file_size']
    def get_uploaded_by_name(self, obj): return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
    def get_file_url(self, obj):
        request = self.context.get('request')
        return request.build_absolute_uri(obj.file.url) if obj.file and request else None

class ProjectListSerializer(drf_serializers.ModelSerializer):
    student_name = drf_serializers.SerializerMethodField()
    supervisor_name = drf_serializers.SerializerMethodField()
    student_matric = drf_serializers.SerializerMethodField()
    milestone_count = drf_serializers.SerializerMethodField()
    completed_milestones = drf_serializers.SerializerMethodField()
    student_avatar = drf_serializers.SerializerMethodField()
    class Meta:
        model = Project
        fields = ['id','title','status','session','student_name','student_matric','student_avatar','supervisor_name','created_at','updated_at','deadline','grade','score','milestone_count','completed_milestones','keywords']
    def get_student_name(self, obj): return obj.student.get_full_name() or obj.student.username
    def get_supervisor_name(self, obj): return obj.supervisor.get_full_name() if obj.supervisor else None
    def get_student_matric(self, obj): return obj.student.matric_number
    def get_student_avatar(self, obj): return obj.student.avatar_initials
    def get_milestone_count(self, obj): return obj.milestones.count()
    def get_completed_milestones(self, obj): return obj.milestones.filter(status='completed').count()

class ProjectDetailSerializer(drf_serializers.ModelSerializer):
    student = UserSerializer(read_only=True)
    supervisor = UserSerializer(read_only=True)
    supervisor_id = drf_serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role='supervisor'), source='supervisor', write_only=True, required=False, allow_null=True)
    milestones = MilestoneSerializer(many=True, read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)
    topic = TopicSerializer(read_only=True)
    topic_id = drf_serializers.PrimaryKeyRelatedField(queryset=Topic.objects.all(), source='topic', write_only=True, required=False, allow_null=True)
    progress_percent = drf_serializers.SerializerMethodField()
    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ['student','created_at','updated_at']
    def get_progress_percent(self, obj):
        total = obj.milestones.count()
        return round((obj.milestones.filter(status='completed').count() / total * 100)) if total else 0

class NotificationSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['recipient','created_at']

class AnnouncementSerializer(drf_serializers.ModelSerializer):
    author_name = drf_serializers.SerializerMethodField()
    class Meta:
        model = Announcement
        fields = '__all__'
        read_only_fields = ['author','created_at']
    def get_author_name(self, obj): return obj.author.get_full_name() or obj.author.username

# ====================== VIEWS ======================
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': UserSerializer(user).data}, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': UserSerializer(user).data})

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        request.user.auth_token.delete()
        return Response({'message': 'Logged out successfully'})

class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    def get_object(self): return self.request.user

class UserListView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        role = self.request.query_params.get('role')
        qs = User.objects.all()
        return qs.filter(role=role) if role else qs

# Dashboard, Stats, Topics, Announcements, Notifications
class DashboardView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        if request.user.role == 'student':
            project = Project.objects.filter(student=request.user).first()
            return Response({'my_project': ProjectDetailSerializer(project, context={'request': request}).data if project else None})
        elif request.user.role == 'supervisor':
            projects = Project.objects.filter(supervisor=request.user)
            return Response({'supervised_projects': ProjectListSerializer(projects, many=True, context={'request': request}).data})
        else:
            return Response({
                'total_projects': Project.objects.count(),
                'total_students': User.objects.filter(role='student').count(),
                'recent_projects': ProjectListSerializer(Project.objects.all()[:5], many=True, context={'request': request}).data
            })

class StatsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        by_status = {status: {'count': Project.objects.filter(status=status).count(), 'label': label} for status, label in Project._meta.get_field('status').choices}
        return Response({
            'total': Project.objects.count(),
            'total_students': User.objects.filter(role='student').count(),
            'total_supervisors': User.objects.filter(role='supervisor').count(),
            'by_status': by_status,
            'sessions': list(Project.objects.values_list('session', flat=True).distinct())
        })

class TopicListView(generics.ListCreateAPIView):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    permission_classes = [IsAuthenticated]

class AnnouncementListCreateView(generics.ListCreateAPIView):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]
    def perform_create(self, serializer): serializer.save(author=self.request.user)

class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self): return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')
    def post(self, request):  # mark all read
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'All marked as read'})

# Projects + Nested endpoints
class ProjectListView(generics.ListCreateAPIView):
    serializer_class = ProjectListSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        user = self.request.user
        if user.role == 'student': return Project.objects.filter(student=user)
        if user.role == 'supervisor': return Project.objects.filter(supervisor=user)
        return Project.objects.all()

class ProjectDetailView(generics.RetrieveUpdateAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectDetailSerializer
    permission_classes = [IsAuthenticated]

class ProjectMilestonesView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        return Response(MilestoneSerializer(project.milestones.all(), many=True).data)
    def post(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        serializer = MilestoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(project=project)
        return Response(serializer.data, status=201)

class ProjectCommentsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        return Response(CommentSerializer(project.comments.all(), many=True).data)
    def post(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(project=project, author=request.user)
        return Response(serializer.data, status=201)

class ProjectDocumentsView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        return Response(DocumentSerializer(project.documents.all(), many=True, context={'request': request}).data)
    def post(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        data = request.data.copy()
        serializer = DocumentSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        doc = serializer.save(uploaded_by=request.user, project=project, file_size=request.FILES.get('file').size if 'file' in request.FILES else 0)
        return Response(DocumentSerializer(doc, context={'request': request}).data, status=201)

# ====================== URLS ======================
def spa_view(request):
    tmpl = os.path.join(os.path.dirname(__file__), 'index.html')
    with open(tmpl, 'r', encoding='utf-8') as f:
        content = f.read()
    return HttpResponse(content, content_type='text/html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/login/', LoginView.as_view()),
    path('api/auth/register/', RegisterView.as_view()),
    path('api/auth/logout/', LogoutView.as_view()),
    path('api/auth/profile/', ProfileView.as_view()),
    path('api/users/', UserListView.as_view()),
    path('api/dashboard/', DashboardView.as_view()),
    path('api/stats/', StatsView.as_view()),
    path('api/topics/', TopicListView.as_view()),
    path('api/announcements/', AnnouncementListCreateView.as_view()),
    path('api/notifications/', NotificationListView.as_view()),
    path('api/projects/', ProjectListView.as_view()),
    path('api/projects/<int:pk>/', ProjectDetailView.as_view()),
    path('api/projects/<int:project_id>/milestones/', ProjectMilestonesView.as_view()),
    path('api/projects/<int:project_id>/comments/', ProjectCommentsView.as_view()),
    path('api/projects/<int:project_id>/documents/', ProjectDocumentsView.as_view()),
    re_path(r'^(?!api/)(?!admin/)(?!static/)(?!media/).*$', spa_view),
]

# ====================== RUN + SEED ======================
if __name__ == "__main__":
    os.makedirs('media/documents', exist_ok=True)
    print("🚀 FUDMA CS Project Management Unit — Single File Mode")
    from django.core.management import call_command
    call_command('makemigrations', '--no-input', verbosity=0)
    call_command('migrate', '--no-input', verbosity=0)

    if not User.objects.filter(username='admin').exists():
        print("🌱 Seeding demo data...")
        admin_user = User.objects.create_superuser('admin', 'admin@fudma.edu.ng', 'admin123', role='admin')
        User.objects.create_user('coordinator', 'coord@fudma.edu.ng', 'coord123', role='coordinator')
        supervisor = User.objects.create_user('dr_ibrahim', 'dr_ibrahim@fudma.edu.ng', 'super123', role='supervisor', first_name='Ibrahim')
        student = User.objects.create_user('ali_musa', 'ali_musa@fudma.edu.ng', 'student123', role='student', first_name='Ali', last_name='Musa', matric_number='CS/23/1234', level='400L', session='2023/2024')

        topic = Topic.objects.create(title="AI Student Performance Predictor", description="Machine learning model for predicting student grades")
        project = Project.objects.create(title="Smart Campus Mobile App", status='in_progress', session='2023/2024', student=student, supervisor=supervisor, topic=topic, deadline='2024-05-30')
        Milestone.objects.create(project=project, title="Requirement Gathering", status='completed')
        Milestone.objects.create(project=project, title="UI/UX Design", status='completed')
        Milestone.objects.create(project=project, title="Backend Development", status='in_progress')
        Announcement.objects.create(author=admin_user, title="Mid-Semester Review", body="Submit your progress reports by April 10", target_role='student', is_pinned=True)
        Notification.objects.create(recipient=student, title="Project Assigned", message="You have been assigned to Dr. Ibrahim", notif_type='assignment')

    print("✅ Ready! http://localhost:8000")
    call_command('runserver', '0.0.0.0:8000')
