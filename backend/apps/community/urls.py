from django.urls import path

from . import views

urlpatterns = [
    path("blogs/<str:address>/posts/<int:no>/comments", views.PostCommentsView.as_view()),
    path("blogs/<str:address>/posts/<int:no>/like", views.PostLikeView.as_view()),
    path("blogs/<str:address>/subscription", views.SubscriptionView.as_view()),
    path("comments/<int:comment_id>", views.CommentDetailView.as_view()),
    path("me/feed", views.FeedView.as_view()),
    path("blogs/<str:address>/manage/comments", views.ManageCommentsView.as_view()),
    path("blogs/<str:address>/manage/guestbook", views.ManageGuestbookView.as_view()),
    path("me/subscriptions", views.MySubscriptionsView.as_view()),
    path("blogs/<str:address>/guestbook", views.GuestbookView.as_view()),
    path("guestbook/<int:entry_id>", views.GuestbookDetailView.as_view()),
]
