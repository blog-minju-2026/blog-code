from django.urls import path

from . import views

urlpatterns = [
    path("images", views.ImageUploadView.as_view()),
    path("topics", views.TopicListView.as_view()),
    path("topics/<slug:slug>/posts", views.TopicPostsView.as_view()),
    path("home/new-posts", views.NewPostsView.as_view()),
    path("search/posts", views.SearchPostsView.as_view()),
    path("search/blogs", views.SearchBlogsView.as_view()),
    path("blogs/<str:address>/posts", views.BlogPostsView.as_view()),
    path("blogs/<str:address>/posts/<int:no>", views.PostDetailView.as_view()),
    path("blogs/<str:address>/drafts", views.DraftsView.as_view()),
    path("blogs/<str:address>/drafts/<int:draft_id>", views.DraftDetailView.as_view()),
    path("blogs/<str:address>/drafts/<int:draft_id>/publish", views.DraftPublishView.as_view()),
    path("blogs/<str:address>/posts/<int:no>/views", views.PostViewCountView.as_view()),
    path("blogs/<str:address>/categories", views.CategoriesView.as_view()),
    path("blogs/<str:address>/categories/order", views.CategoryOrderView.as_view()),
    path("blogs/<str:address>/categories/<int:category_id>", views.CategoryDetailView.as_view()),
    path("blogs/<str:address>/tags", views.TagsView.as_view()),
]
