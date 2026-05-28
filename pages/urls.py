# urls.py

from django.urls import path
from . import views

urlpatterns = [
    path("",                        views.accueil,               name="accueil"),
    path("vols/",                   views.billet,                name="billet"),

    # API
    path("api/flights/",            views.search_flights,        name="search_flights"),
    path("api/payment-intent/",     views.create_payment_intent, name="payment_intent"),
    path("api/book/",               views.book_flight,           name="book_flight"),
    path("contact/",           views.contact,            name="contact"),
    path("contact/soumettre/", views.soumettre_contact,  name="soumettre_contact"),
    path("hotels/",            views.hotels,             name="hotels"),
    path("api/webhook/stripe/", views.stripe_webhook,   name="stripe_webhook"),
    path("devis/",           views.devis,           name="devis"),
    path("api/devis/",       views.soumettre_devis,  name="soumettre_devis"),
    # Test de connexion — à appeler en premier pour valider vos clés
    # ===== API HÔTELS (HotelBeds) =====
    path("hotels/ping/",                           views.hotel_ping,            name="hotel_ping"),
    path("hotels/search/",                         views.hotel_search,          name="hotel_search"),
    path("hotels/checkrate/",                      views.hotel_checkrate,       name="hotel_checkrate"),
    path("hotels/book/",                           views.hotel_book,            name="hotel_book"),
    path("hotels/booking/<str:reference>/",        views.hotel_booking_detail,  name="hotel_booking_detail"),
    path("hotels/booking/<str:reference>/cancel/", views.hotel_booking_cancel,  name="hotel_booking_cancel"),
]
