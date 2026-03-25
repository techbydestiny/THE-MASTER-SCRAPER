# leads/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.homepage, name='homepage'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('search/', views.search_results, name='search'),
    path('export/', views.export_csv, name='export'),
    path('clear/', views.clear_leads, name='clear'),
    path('test-api/', views.test_api, name='test_api'),
    path('debug-api/', views.debug_api, name='debug_api'),
]