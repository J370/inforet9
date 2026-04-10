from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.search_results, name='search_results'),
    path('feedback/relevance/', views.submit_relevance_feedback, name='submit_relevance_feedback'),
]
