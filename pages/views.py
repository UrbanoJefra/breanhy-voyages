# views.py — Breavy Voyages (Production Ready)
import json
import uuid
import logging
import requests
import stripe
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Booking, Customer, Payment, SearchLog, ContactMessage, DemandeDevis
from django.views.decorators.http import require_POST
import hashlib
import time
from datetime import datetime, timedelta
from django.views.decorators.cache import cache_page
from django.core.cache import cache




logger = logging.getLogger("breavy")

# ──────────────────────────────────────────
#  CONFIGURATION
# ──────────────────────────────────────────
DUFFEL_TOKEN = settings.DUFFEL_API_KEY
DUFFEL_HEADERS = {
    "Authorization": f"Bearer {DUFFEL_TOKEN}",
    "Duffel-Version": "v2",
    "Content-Type": "application/json",
}

stripe.api_key = settings.STRIPE_SECRET_KEY

IATA_MAP = {
    "paris": "CDG", "marseille": "MRS", "lyon": "LYS", "nice": "NCE",
    "bordeaux": "BOD", "toulouse": "TLS", "nantes": "NTE",
    "brazzaville": "BZV", "pointe noire": "PNR", "pointe-noire": "PNR",
    "kinshasa": "FIH", "libreville": "LBV", "douala": "DLA",
    "yaoundé": "NSI", "yaounde": "NSI", "bangui": "BGF", "luanda": "LAD",
    "bata": "BSG", "dakar": "DSS", "abidjan": "ABJ", "accra": "ACC",
    "lagos": "LOS", "nairobi": "NBO", "zanzibar": "ZNZ",
    "johannesburg": "JNB", "casablanca": "CMN", "tunis": "TUN",
    "addis abeba": "ADD", "cotonou": "COO", "lome": "LFW", "lomé": "LFW",
    "bamako": "BKO", "ouagadougou": "OUA", "conakry": "CKY",
    "kigali": "KGL", "kampala": "EBB", "dar es salaam": "DAR",
    "maputo": "MPM", "antananarivo": "TNR",
    "ile maurice": "MRU", "île maurice": "MRU", "mauritius": "MRU",
    "lisbonne": "LIS", "madrid": "MAD", "barcelone": "BCN",
    "rome": "FCO", "milan": "MXP", "amsterdam": "AMS",
    "bruxelles": "BRU", "geneve": "GVA", "genève": "GVA",
    "zurich": "ZRH", "vienne": "VIE", "prague": "PRG",
    "venise": "VCE", "athenes": "ATH", "athènes": "ATH",
    "istanbul": "IST", "berlin": "BER", "francfort": "FRA",
    "munich": "MUC", "copenhague": "CPH", "stockholm": "ARN",
    "oslo": "OSL", "helsinki": "HEL", "varsovie": "WAW",
    "budapest": "BUD", "londres": "LHR", "london": "LHR",
    "new york": "JFK", "miami": "MIA", "los angeles": "LAX",
    "chicago": "ORD", "houston": "IAH", "boston": "BOS",
    "washington": "IAD", "montreal": "YUL", "toronto": "YYZ",
    "rio de janeiro": "GIG", "sao paulo": "GRU",
    "bogota": "BOG", "bogotá": "BOG", "cartagena": "CTG",
    "lima": "LIM", "buenos aires": "EZE", "santiago": "SCL",
    "punta cana": "PUJ", "cancun": "CUN", "cancún": "CUN",
    "dubai": "DXB", "dubaï": "DXB", "doha": "DOH",
    "abou dhabi": "AUH", "abu dhabi": "AUH", "riyad": "RUH",
    "beyrouth": "BEY", "amman": "AMM", "tel aviv": "TLV",
    "bangkok": "BKK", "bali": "DPS", "tokyo": "NRT",
    "singapour": "SIN", "hong kong": "HKG",
    "beijing": "PEK", "pékin": "PEK", "shanghai": "PVG",
    "seoul": "ICN", "séoul": "ICN", "kuala lumpur": "KUL",
    "jakarta": "CGK", "mumbai": "BOM", "delhi": "DEL", "colombo": "CMB",
    "sal": "SID", "cap vert": "SID", "fuerteventura": "FUE",
    "acores": "PDL", "açores": "PDL", "sao tome": "TMS", "são tomé": "TMS",
}


def resolve_iata(query):
    q = query.strip().lower()
    if len(q) == 3 and q.isalpha():
        return q.upper()
    return IATA_MAP.get(q)


def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _generate_booking_reference():
    return "BV-" + uuid.uuid4().hex[:8].upper()


# ──────────────────────────────────────────
#  VUES PAGES
# ──────────────────────────────────────────
def accueil(request):
    return render(request, "pages/accueil.html")


def billet(request):
    return render(request, "pages/billet.html", {
        "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
    })


# ──────────────────────────────────────────
#  API : RECHERCHE DE VOLS
# ──────────────────────────────────────────
@require_http_methods(["GET"])
def search_flights(request):
    origin_raw      = request.GET.get("origin", "").strip()
    destination_raw = request.GET.get("destination", "").strip()
    date            = request.GET.get("date", "").strip()
    cabin_class     = request.GET.get("cabin_class", "economy").strip()

    try:
        passengers_nb = max(1, min(9, int(request.GET.get("passengers", 1))))
    except (ValueError, TypeError):
        passengers_nb = 1

    origin      = resolve_iata(origin_raw)
    destination = resolve_iata(destination_raw)

    if not origin:
        return JsonResponse({"error": "unknown_city", "details": f"Ville de départ inconnue : '{origin_raw}'"}, status=400)
    if not destination:
        return JsonResponse({"error": "unknown_city", "details": f"Destination inconnue : '{destination_raw}'"}, status=400)
    if not date:
        return JsonResponse({"error": "missing_parameters", "details": "La date est requise."}, status=400)

    passengers = [{"type": "adult"} for _ in range(passengers_nb)]
    payload = {
        "data": {
            "slices": [{"origin": origin, "destination": destination, "departure_date": date}],
            "passengers": passengers,
            "cabin_class": cabin_class,
        }
    }

    try:
        resp = requests.post(
            "https://api.duffel.com/air/offer_requests",
            json=payload,
            headers=DUFFEL_HEADERS,
            timeout=30,
        )
    except requests.exceptions.Timeout:
        logger.error("Duffel timeout : %s → %s le %s", origin, destination, date)
        return JsonResponse({"error": "timeout", "details": "Duffel ne répond pas."}, status=504)
    except requests.exceptions.RequestException as e:
        logger.error("Duffel network error : %s", str(e))
        return JsonResponse({"error": "network_error", "details": str(e)}, status=502)

    if resp.status_code not in (200, 201):
        logger.error("Duffel error %s : %s", resp.status_code, resp.text[:200])
        return JsonResponse({"error": "duffel_error", "details": resp.text}, status=400)

    data   = resp.json()
    offers = data.get("data", {}).get("offers", [])

    try:
        SearchLog.objects.create(
            origin        = origin,
            destination   = destination,
            date          = date,
            cabin_class   = cabin_class,
            passengers    = passengers_nb,
            results_count = len(offers),
            ip_address    = _get_client_ip(request),
        )
    except Exception as e:
        logger.warning("SearchLog non sauvegardé : %s", e)

    return JsonResponse({"offers": offers})


# ──────────────────────────────────────────
#  API : CRÉER UN PAYMENT INTENT STRIPE
# ──────────────────────────────────────────
@require_http_methods(["POST"])
def create_payment_intent(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide"}, status=400)

    amount   = body.get("amount")
    currency = body.get("currency", "EUR").lower()

    if not amount:
        return JsonResponse({"error": "amount manquant"}, status=400)

    try:
        amount_cents = int(float(amount) * 100)
    except (ValueError, TypeError):
        return JsonResponse({"error": "amount invalide"}, status=400)

    if amount_cents < 50:
        return JsonResponse({"error": "Montant trop faible"}, status=400)

    try:
        intent = stripe.PaymentIntent.create(
            amount               = amount_cents,
            currency             = currency,
            automatic_payment_methods   = {"enabled": True},
            metadata             = {"source": "breavy_voyages"},
        )
        return JsonResponse({"client_secret": intent.client_secret})
    except stripe.error.StripeError as e:
        logger.error("Stripe PaymentIntent error : %s", str(e))
        return JsonResponse({"error": str(e)}, status=400)


# ──────────────────────────────────────────
#  API : RÉSERVATION COMPLÈTE
# ──────────────────────────────────────────
@require_http_methods(["POST"])
def book_flight(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide"}, status=400)

    required = [
        "offer_id", "passenger_id", "first_name", "last_name",
        "email", "phone", "born_on", "title", "gender",
        "amount", "currency", "payment_intent_id",
    ]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return JsonResponse({"error": f"Champs manquants : {', '.join(missing)}"}, status=400)

    # ── ÉTAPE 1 : Vérifier le PaymentIntent Stripe ──
    try:
        intent = stripe.PaymentIntent.retrieve(body["payment_intent_id"])
        if intent.status != "succeeded":
            return JsonResponse(
                {"error": f"Paiement non finalisé (statut : {intent.status})"},
                status=400,
            )
    except stripe.error.StripeError as e:
        logger.error("Stripe retrieve error : %s", str(e))
        return JsonResponse({"error": f"Erreur Stripe : {str(e)}"}, status=400)

    # ── Anti double-soumission ──
    existing = Booking.objects.filter(
        stripe_payment_intent_id=body["payment_intent_id"]
    ).first()
    if existing:
        logger.info("Double soumission détectée pour PI %s", body["payment_intent_id"])
        return JsonResponse({"booking_reference": existing.booking_reference}, status=200)

    # ── ÉTAPE 2 : Créer la réservation Duffel ──
    duffel_passenger = {
        "id":           body["passenger_id"],
        "title":        body["title"],
        "gender":       body["gender"],
        "given_name":   body["first_name"],
        "family_name":  body["last_name"],
        "born_on":      body["born_on"],
        "email":        body["email"],
        "phone_number": body["phone"],
    }

    if body.get("doc_type") and body.get("doc_number") and body.get("doc_expiry"):
        duffel_passenger["identity_documents"] = [{
            "type":              body["doc_type"],
            "unique_identifier": body["doc_number"],
            "expires_on":        body["doc_expiry"],
        }]

    duffel_payload = {
        "data": {
            "selected_offers": [body["offer_id"]],
            "passengers":      [duffel_passenger],
            "payments": [{
                "type":     "balance",
                "currency": body["currency"],
                "amount":   body["amount"],
            }],
            "metadata": {
                "stripe_payment_intent": body["payment_intent_id"],
            },
        }
    }

    try:
        resp = requests.post(
            "https://api.duffel.com/air/orders",
            json=duffel_payload,
            headers=DUFFEL_HEADERS,
            timeout=30,
        )
    except requests.exceptions.Timeout:
        logger.error("Duffel order timeout pour PI %s", body["payment_intent_id"])
        # Paiement OK mais réservation non créée : alerte ops
        _alert_ops(
            subject="⚠️ URGENT : Paiement OK mais réservation Duffel timeout",
            message=f"PaymentIntent : {body['payment_intent_id']}\nMontant : {body['amount']} {body['currency']}\nClient : {body['email']}",
        )
        return JsonResponse({"error": "Duffel timeout — réservation non créée. Notre équipe vous contacte sous 1h."}, status=504)
    except requests.exceptions.RequestException as e:
        logger.error("Duffel order network error : %s", str(e))
        _alert_ops(
            subject="⚠️ URGENT : Erreur réseau Duffel après paiement",
            message=f"Erreur : {str(e)}\nPI : {body['payment_intent_id']}\nClient : {body['email']}",
        )
        return JsonResponse({"error": f"Erreur réseau Duffel : {str(e)}"}, status=502)

    duffel_data = resp.json()

    if resp.status_code not in (200, 201):
        logger.error("Duffel order error %s : %s", resp.status_code, str(duffel_data)[:300])
        _alert_ops(
            subject="⚠️ URGENT : Paiement OK mais réservation Duffel échouée",
            message=f"PI : {body['payment_intent_id']}\nMontant : {body['amount']} {body['currency']}\nClient : {body['email']}\nErreur Duffel : {str(duffel_data)[:500]}",
        )
        return JsonResponse({"error": "Réservation non confirmée. Notre équipe vous contacte sous 1h."}, status=400)

    order       = duffel_data.get("data", {})
    booking_ref = order.get("booking_reference") or _generate_booking_reference()
    order_id    = order.get("id", "")

    try:
        departure_date = order["slices"][0]["segments"][0]["departing_at"][:10]
        airline        = order["slices"][0]["segments"][0]["marketing_carrier"]["name"]
    except (KeyError, IndexError, TypeError):
        departure_date = None
        airline        = ""

    # ── ÉTAPE 3 : Sauvegarder en base ──
    customer, _ = Customer.objects.get_or_create(
        email=body["email"],
        defaults={
            "first_name": body["first_name"],
            "last_name":  body["last_name"],
            "phone":      body["phone"],
        },
    )

    booking = Booking.objects.create(
        customer                 = customer,
        booking_reference        = booking_ref,
        duffel_order_id          = order_id,
        offer_id                 = body["offer_id"],
        origin                   = body.get("origin", ""),
        destination              = body.get("destination", ""),
        departure_date           = departure_date,
        airline                  = airline,
        first_name               = body["first_name"],
        last_name                = body["last_name"],
        email                    = body["email"],
        phone                    = body["phone"],
        born_on                  = body["born_on"],
        passport_number          = body.get("doc_number", ""),
        passport_expiry          = body.get("doc_expiry") or None,
        stripe_payment_intent_id = body["payment_intent_id"],
        amount                   = body["amount"],
        currency                 = body["currency"],
        status                   = "confirmed",
        baggage_option           = body.get("baggage_option", "included"),
    )

    Payment.objects.create(
        booking                  = booking,
        stripe_payment_intent_id = body["payment_intent_id"],
        amount                   = body["amount"],
        currency                 = body["currency"],
        status                   = "succeeded",
        paid_at                  = timezone.now(),
    )

    logger.info("Réservation créée : %s | %s → %s | %s %s | %s",
                booking_ref, body.get("origin"), body.get("destination"),
                body["amount"], body["currency"], body["email"])

    # ── ÉTAPE 4 : Emails ──
    _send_confirmation_email(
        to_email    = body["email"],
        first_name  = body["first_name"],
        booking_ref = booking_ref,
        route       = f"{body.get('origin', '')} → {body.get('destination', '')}",
        amount      = body["amount"],
        currency    = body["currency"],
        airline     = airline,
        departure   = departure_date or "",
    )

    return JsonResponse({
        "booking_reference": booking_ref,
        "order_id":          order_id,
    })


# ──────────────────────────────────────────
#  WEBHOOK STRIPE
# ──────────────────────────────────────────
@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    payload    = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.warning("Webhook Stripe : payload invalide")
        return JsonResponse({"error": "Invalid payload"}, status=400)
    except stripe.error.SignatureVerificationError:
        logger.warning("Webhook Stripe : signature invalide")
        return JsonResponse({"error": "Invalid signature"}, status=400)

    if event["type"] == "payment_intent.succeeded":
        pi = event["data"]["object"]
        pi_id = pi.get("id", "")

        if not Booking.objects.filter(stripe_payment_intent_id=pi_id).exists():
            logger.error("WEBHOOK : paiement %s sans réservation associée !", pi_id)
            _alert_ops(
                subject="⚠️ URGENT : Paiement Stripe reçu sans réservation",
                message=f"PaymentIntent : {pi_id}\nMontant : {pi.get('amount', 0) / 100} {pi.get('currency', '').upper()}\nMétadonnées : {pi.get('metadata', {})}",
            )

    elif event["type"] == "payment_intent.payment_failed":
        pi = event["data"]["object"]
        logger.warning("Paiement échoué : %s", pi.get("id"))

    return JsonResponse({"status": "ok"})


# ──────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────
def _send_confirmation_email(to_email, first_name, booking_ref, route, amount, currency, airline="", departure=""):
    subject = f"✈ Confirmation de réservation — {booking_ref}"
    message = f"""Bonjour {first_name},

Votre réservation est confirmée !

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Référence : {booking_ref}
  Vol       : {route}
  Compagnie : {airline}
  Départ    : {departure}
  Montant   : {amount} {currency}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Conservez cette référence pour votre enregistrement en ligne.
Présentez-vous à l'aéroport avec votre pièce d'identité.

Pour toute question : contact@breavyvoyages.com
Support WhatsApp : +242 06 XXX XXXX

Bon voyage !
L'équipe Breavy Voyages
"""
    try:
        send_mail(
            subject        = subject,
            message        = message,
            from_email     = settings.DEFAULT_FROM_EMAIL,
            recipient_list = [to_email],
            fail_silently  = False,
        )
        logger.info("Email de confirmation envoyé à %s", to_email)
    except Exception as e:
        logger.error("Email non envoyé à %s : %s", to_email, e)


def _alert_ops(subject, message):
    """Envoie une alerte à l'équipe opérationnelle."""
    try:
        send_mail(
            subject        = subject,
            message        = message,
            from_email     = settings.DEFAULT_FROM_EMAIL,
            recipient_list = [settings.OPS_EMAIL],
            fail_silently  = True,
        )
    except Exception as e:
        logger.error("Alerte ops non envoyée : %s", e)

def devis(request):
    """Affiche la page de demande de devis."""
    return render(request, "pages/devis.html")

def hotels(request):
    """Affiche la page de demande de devis."""
    return render(request, "pages/hotels.html")

def contact(request):
    """Affiche la page de demande de devis."""
    return render(request, "pages/contact.html")

@require_POST
def soumettre_contact(request):
    """Reçoit le formulaire contact en JSON et enregistre en base."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Données invalides.'}, status=400)
 
    # ── Extraction ──────────────────────────────────────────────
    nom     = data.get('nom', '').strip()
    email   = data.get('email', '').strip()
    sujet   = data.get('sujet', '').strip()
    message = data.get('message', '').strip()
 
    # ── Validation serveur ───────────────────────────────────────
    errors = {}
 
    if len(nom) < 2:
        errors['nom'] = 'Le nom doit contenir au moins 2 caractères.'
 
    if not email or '@' not in email:
        errors['email'] = 'Adresse email invalide.'
 
    if len(sujet) < 3:
        errors['sujet'] = 'Le sujet doit contenir au moins 3 caractères.'
 
    if len(message) < 10:
        errors['message'] = 'Le message doit contenir au moins 10 caractères.'
 
    if len(sujet) > 150:
        errors['sujet'] = 'Le sujet ne doit pas dépasser 150 caractères.'
 
    if len(message) > 10_000:
        errors['message'] = 'Le message ne doit pas dépasser 10 000 caractères.'
 
    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=422)
 
    # ── Enregistrement ───────────────────────────────────────────
    try:
        contact_msg = ContactMessage.objects.create(
            nom=nom,
            email=email,
            sujet=sujet,
            message=message,
            # traite=False par défaut (défini dans le modèle)
        )
    except Exception as e:
        return JsonResponse(
            {'success': False, 'error': 'Erreur lors de l\'enregistrement. Veuillez réessayer.'},
            status=500
        )
 
    return JsonResponse({
        'success': True,
        'message': 'Votre message a bien été enregistré.',
        'id': contact_msg.pk,
    }, status=201)
 
 
# ──────────────────────────────────────────
#  API : SOUMETTRE UN DEVIS
# ──────────────────────────────────────────
@require_http_methods(["POST"])
def soumettre_devis(request):
    """
    Reçoit la demande de devis, la sauvegarde en base
    et envoie les emails de notification.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON invalide"}, status=400)
 
    # Validation des champs obligatoires
    required = ["nom", "email", "telephone", "destination",
                "date_depart", "date_retour", "nombre_voyageurs", "type_voyage"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return JsonResponse({
            "success": False,
            "error": f"Champs manquants : {', '.join(missing)}"
        }, status=400)
 
    # Validation dates
    from datetime import date
    try:
        dep = date.fromisoformat(body["date_depart"])
        ret = date.fromisoformat(body["date_retour"])
        if ret <= dep:
            return JsonResponse({
                "success": False,
                "error": "La date de retour doit être après la date de départ."
            }, status=400)
    except ValueError:
        return JsonResponse({"success": False, "error": "Dates invalides."}, status=400)
 
    # Génération d'une référence unique
    reference = "DV-" + uuid.uuid4().hex[:8].upper()
 
    # Sauvegarde en base
    try:
        devis_obj = DemandeDevis.objects.create(
            nom              = body["nom"],
            email            = body["email"],
            telephone        = body["telephone"],
            destination      = body["destination"],
            date_depart      = body["date_depart"],
            date_retour      = body["date_retour"],
            nombre_voyageurs = int(body["nombre_voyageurs"]),
            type_voyage      = body["type_voyage"],
            budget           = body.get("budget") or None,
            message          = body.get("message", ""),
        )
        logger.info("Devis créé : %s | %s → %s | %s",
                    reference, body["nom"], body["destination"], body["email"])
    except Exception as e:
        logger.error("Erreur création devis : %s", str(e))
        return JsonResponse({
            "success": False,
            "error": "Erreur serveur. Veuillez réessayer."
        }, status=500)
 
    # Email de confirmation au client
    _send_devis_confirmation_client(
        to_email    = body["email"],
        nom         = body["nom"],
        reference   = reference,
        destination = body["destination"],
        date_depart = body["date_depart"],
        date_retour = body["date_retour"],
        voyageurs   = body["nombre_voyageurs"],
        type_voyage = body["type_voyage"],
    )
 
    # Email de notification interne (ops)
    _send_devis_notification_ops(body=body, reference=reference)
 
    return JsonResponse({"success": True, "reference": reference})
 
 
# ──────────────────────────────────────────
#  HELPERS EMAIL DEVIS
# ──────────────────────────────────────────
def _send_devis_confirmation_client(to_email, nom, reference, destination,
                                     date_depart, date_retour, voyageurs, type_voyage):
    """Email envoyé au client pour confirmer la réception de sa demande."""
    types_labels = {
        "famille":   "Voyage en famille",
        "couple":    "Voyage en couple",
        "business":  "Voyage business",
        "groupe":    "Voyage en groupe",
        "lune_miel": "Lune de miel",
    }
    subject = f"✈ Votre demande de devis a été reçue — {reference}"
    message = f"""Bonjour {nom},
 
Nous avons bien reçu votre demande de devis. Merci de nous faire confiance !
 
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Référence       : {reference}
  Destination     : {destination}
  Départ          : {date_depart}
  Retour          : {date_retour}
  Voyageurs       : {voyageurs}
  Type de voyage  : {types_labels.get(type_voyage, type_voyage)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 
Nos experts analysent votre demande et vous enverront une proposition
complète et personnalisée dans les 24 heures ouvrées.
 
Pour toute question urgente :
📱 WhatsApp : +242 06 XXX XXXX
✉  Email    : contact@breavyvoyages.com
 
À très bientôt !
L'équipe Breavy Voyages
"""
    try:
        send_mail(
            subject        = subject,
            message        = message,
            from_email     = settings.DEFAULT_FROM_EMAIL,
            recipient_list = [to_email],
            fail_silently  = False,
        )
        logger.info("Email confirmation devis envoyé à %s", to_email)
    except Exception as e:
        logger.error("Email devis client non envoyé à %s : %s", to_email, e)
 
 
def _send_devis_notification_ops(body, reference):
    """Email envoyé à l'équipe pour traiter la demande en interne."""
    subject = f"📋 Nouvelle demande de devis — {reference} — {body.get('destination', '')}"
    message = f"""Nouvelle demande de devis reçue !
 
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Référence       : {reference}
  Client          : {body.get('nom', '')}
  Email           : {body.get('email', '')}
  Téléphone       : {body.get('telephone', '')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Destination     : {body.get('destination', '')}
  Départ          : {body.get('date_depart', '')}
  Retour          : {body.get('date_retour', '')}
  Voyageurs       : {body.get('nombre_voyageurs', '')}
  Type de voyage  : {body.get('type_voyage', '')}
  Budget estimé   : {body.get('budget', 'Non précisé')} €
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Message client  :
  {body.get('message', '(aucun message)') or '(aucun message)'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 
⏰ À traiter dans les 24h.
Admin Django : https://breavyvoyages.com/admin/voyages/demandedevis/
"""
    try:
        send_mail(
            subject        = subject,
            message        = message,
            from_email     = settings.DEFAULT_FROM_EMAIL,
            recipient_list = [settings.OPS_EMAIL],
            fail_silently  = True,
        )
    except Exception as e:
        logger.error("Email devis ops non envoyé : %s", e)



"""
views.py — Intégration HotelBeds API
=====================================
Flux couverts (requis pour certification étape 3) :
  1. /hotels/search/          → Availability (recherche hôtels)
  2. /hotels/checkrate/       → CheckRate (vérification tarif)
  3. /hotels/book/            → Booking (réservation)
  4. /hotels/booking/<ref>/   → BookingDetail (détail réservation)
  5. /hotels/cancel/<ref>/    → BookingCancel (annulation)

Configuration requise dans settings.py ou .env :
  HOTELBEDS_API_KEY    = "votre_api_key"
  HOTELBEDS_SECRET     = "votre_secret"
  HOTELBEDS_ENV        = "test"   # "test" ou "live"
"""

# ──────────────────────────────────────────
#  CONFIG HOTELBEDS
# ──────────────────────────────────────────
 
# Environnement TEST  → "https://api.test.hotelbeds.com"
# Environnement LIVE  → "https://api.hotelbeds.com"
HOTELBEDS_BASE = "https://api.test.hotelbeds.com"   # ← changer en LIVE pour la production
 
 
def _hb_headers():
    """Génère les headers HMAC-SHA256 requis par HotelBeds."""
    api_key   = settings.HOTELBEDS_API       # HotelBeds_API dans .env → settings
    secret    = settings.HOTELBEDS_SECRET    # HotelBeds_SECRET dans .env → settings
    timestamp = str(int(time.time()))
    signature = hashlib.sha256(
        (api_key + secret + timestamp).encode("utf-8")
    ).hexdigest()
    return {
        "Api-key":        api_key,
        "X-Signature":    signature,
        "Accept":         "application/json",
        "Accept-Encoding":"gzip",
        "Content-Type":   "application/json",
    }
 
 
# Dictionnaire IATA/ville → code destination HotelBeds (GIATA zone)
# HotelBeds utilise des codes de zones. On fait d'abord un appel à leur API
# "locations" pour résoudre la destination saisie par l'utilisateur.
def _resolve_destination(query: str) -> dict | None:
    """
    Cherche le code de destination HotelBeds à partir d'un texte libre.
    Retourne {"code": "...", "name": "...", "type": "..."} ou None.
    """
    try:
        resp = requests.get(
            f"{HOTELBEDS_BASE}/hotel-content-api/1.0/locations/destinations",
            headers=_hb_headers(),
            params={"fields": "all", "language": "FRA", "from": 1, "to": 5},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        destinations = data.get("destinations", [])
        q = query.strip().lower()
        for dest in destinations:
            if q in (dest.get("name", "").lower()):
                return {"code": dest["code"], "name": dest["name"], "type": "zone"}
    except Exception as e:
        logger.warning("HotelBeds destination resolve error: %s", e)
    return None
 
 
# Mapping direct ville → code destination HotelBeds
HOTELBEDS_DEST_MAP = {
    "dubai": "DXB", "dubaï": "DXB",
    "paris": "PAR",
    "london": "LON", "londres": "LON",
    "lisbonne": "LIS", "lisbon": "LIS",
    "barcelone": "BCN", "barcelona": "BCN",
    "rome": "ROM", "roma": "ROM",
    "amsterdam": "AMS",
    "berlin": "BER",
    "madrid": "MAD",
    "marrakech": "RAK",
    "zanzibar": "ZNZ",
    "mauritius": "MRU", "île maurice": "MRU", "ile maurice": "MRU",
    "maldives": "MLE",
    "bangkok": "BKK",
    "phuket": "HKT",
    "bali": "DPS",
    "new york": "NYC",
    "miami": "MIA",
    "cancun": "CUN", "cancún": "CUN",
    "punta cana": "PUJ",
    "singapore": "SIN", "singapour": "SIN",
    "tokyo": "TYO",
    "sydney": "SYD",
    "nairobi": "NBO",
    "cap-vert": "SID", "cap vert": "SID",
    "santorin": "JTR", "santorini": "JTR",
    "mykonos": "JMK",
    "ibiza": "IBZ",
    "mallorca": "PMI", "majorque": "PMI",
    "tenerife": "TFN",
    "algarve": "FAO",
    "porto": "OPO",
    "venise": "VCE", "venice": "VCE",
}

def _search_destination_code(query: str) -> str | None:
    q = query.strip().lower()

    # 1. Correspondance exacte
    if q in HOTELBEDS_DEST_MAP:
        return HOTELBEDS_DEST_MAP[q]

    # 2. Correspondance partielle
    for key, code in HOTELBEDS_DEST_MAP.items():
        if key in q or q in key:
            return code

    # 3. Appel API HotelBeds avec pagination large
    try:
        resp = requests.get(
            f"{HOTELBEDS_BASE}/hotel-content-api/1.0/locations/destinations",
            headers=_hb_headers(),
            params={"fields": "code,name", "language": "ENG", "from": 1, "to": 100},
            timeout=15,
        )
        if resp.status_code == 200:
            for d in resp.json().get("destinations", []):
                if query.strip().lower() in d.get("name", "").lower():
                    return d["code"]
    except Exception as e:
        logger.warning("HotelBeds destination API: %s", e)

    return None
 
 
# ──────────────────────────────────────────
#  VUE : PAGE HÔTELS
# ──────────────────────────────────────────
def hotels(request):
    return render(request, "pages/hotels.html")
 
 
# ──────────────────────────────────────────
#  VUE : PING (test de connexion)
# ──────────────────────────────────────────
@require_http_methods(["GET"])
def hotel_ping(request):
    """Vérifie que les clés HotelBeds fonctionnent."""
    try:
        resp = requests.get(
            f"{HOTELBEDS_BASE}/hotel-api/1.0/status",
            headers=_hb_headers(),
            timeout=10,
        )
        return JsonResponse({
            "status":      "ok" if resp.status_code == 200 else "error",
            "http_status": resp.status_code,
            "response":    resp.json() if resp.status_code == 200 else resp.text[:300],
            "environment": "TEST" if "test" in HOTELBEDS_BASE else "LIVE",
        })
    except Exception as e:
        return JsonResponse({"status": "error", "details": str(e)}, status=502)
 
 
# ──────────────────────────────────────────
#  VUE : RECHERCHE D'HÔTELS
# ──────────────────────────────────────────
@require_http_methods(["GET"])
def hotel_search(request):
    """
    GET /hotels/search/?destination=Paris&check_in=2026-06-15&check_out=2026-06-17&adults=2&rooms=1
    """
    destination = request.GET.get("destination", "").strip()
    check_in    = request.GET.get("check_in", "").strip()
    check_out   = request.GET.get("check_out", "").strip()
 
    try:
        adults = max(1, min(9, int(request.GET.get("adults", 2))))
        rooms  = max(1, min(5, int(request.GET.get("rooms", 1))))
    except (ValueError, TypeError):
        adults, rooms = 2, 1
 
    if not destination:
        return JsonResponse({"error": "missing_destination", "details": "La destination est requise."}, status=400)
    if not check_in or not check_out:
        return JsonResponse({"error": "missing_dates", "details": "Les dates sont requises."}, status=400)
    if check_in >= check_out:
        return JsonResponse({"error": "invalid_dates", "details": "La date de départ doit être après l'arrivée."}, status=400)
 
    # Résolution de la destination
    dest_code = _search_destination_code(destination)
    if not dest_code:
        return JsonResponse({
            "error":   "unknown_destination",
            "details": f"Destination inconnue : '{destination}'. Essayez un nom de ville en anglais (ex: Paris, London, Dubai)."
        }, status=400)
 
    # Construction payload HotelBeds
    payload = {
        "stay": {
            "checkIn":  check_in,
            "checkOut": check_out,
        },
        "occupancies": [
            {"rooms": rooms, "adults": adults, "children": 0}
        ],
        "destination": {"code": dest_code},
        "filter": {"maxHotels": 50},
        "reviews": [{"type": "HOTELBEDS", "maxRate": 5, "minReviewCount": 3}],
    }
 
    try:
        resp = requests.post(
            f"{HOTELBEDS_BASE}/hotel-api/1.0/hotels",
            json=payload,
            headers=_hb_headers(),
            timeout=30,
        )
    except requests.exceptions.Timeout:
        return JsonResponse({"error": "timeout", "details": "HotelBeds ne répond pas."}, status=504)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": "network_error", "details": str(e)}, status=502)
 
    if resp.status_code not in (200, 201):
        logger.error("HotelBeds search error %s: %s", resp.status_code, resp.text[:300])
        return JsonResponse({
            "error":   "hotelbeds_error",
            "details": resp.json().get("error", {}).get("message", resp.text[:200])
        }, status=400)
 
    data   = resp.json()
    hotels = data.get("hotels", {}).get("hotels", [])
 
    # Formater la réponse pour le frontend
    formatted = []
    for h in hotels:
        min_rate = None
        rooms_list = []
        for room in h.get("rooms", []):
            for rate in room.get("rates", []):
                price = float(rate.get("net", rate.get("sellingRate", 0)))
                if min_rate is None or price < min_rate:
                    min_rate = price
            rooms_list.append({
                "code":  room.get("code"),
                "name":  room.get("name"),
                "rates": [
                    {
                        "rateKey":              rate.get("rateKey"),
                        "net":                  rate.get("net"),
                        "sellingRate":          rate.get("sellingRate"),
                        "boardCode":            rate.get("boardCode"),
                        "boardName":            rate.get("boardName"),
                        "cancellationPolicies": rate.get("cancellationPolicies", []),
                        "rateType":             rate.get("rateType"),
                    }
                    for rate in room.get("rates", [])
                ],
            })
 
        # Images — HotelBeds renvoie des paths, on construit l'URL complète
        images = []
        for img in h.get("images", [])[:3]:
            path = img.get("path", "")
            if path:
                images.append(f"https://photos.hotelbeds.com/giata/bigger/{path}")
 
        formatted.append({
            "code":            h.get("code"),
            "name":            h.get("name"),
            "categoryCode":    h.get("categoryCode"),
            "categoryName":    h.get("categoryName"),
            "destinationCode": h.get("destinationCode"),
            "destinationName": h.get("destinationName"),
            "zoneName":        h.get("zoneName"),
            "address":         h.get("address", {}).get("content", ""),
            "city":            h.get("city", {}).get("content", ""),
            "countryCode":     h.get("countryCode"),
            "longitude":       h.get("longitude"),
            "latitude":        h.get("latitude"),
            "minRate":         str(min_rate) if min_rate else "—",
            "currency":        h.get("currency"),
            "images":          images,
            "facilities":      [f.get("facilityName", "") for f in h.get("facilities", [])[:6]],
            "rooms":           rooms_list,
        })
 
    return JsonResponse({"hotels": formatted, "destination_code": dest_code})
 
 
# ──────────────────────────────────────────
#  VUE : CHECKRATE (obligatoire avant réservation)
# ──────────────────────────────────────────
@require_http_methods(["POST"])
def hotel_checkrate(request):
    """
    POST /hotels/checkrate/
    Body: { "rate_key": "..." }
    Vérifie le tarif en temps réel avant de passer la réservation.
    Étape OBLIGATOIRE selon HotelBeds.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide"}, status=400)
 
    rate_key = body.get("rate_key")
    if not rate_key:
        return JsonResponse({"error": "rate_key manquant"}, status=400)
 
    payload = {"rooms": [{"rateKey": rate_key}]}
 
    try:
        resp = requests.post(
            f"{HOTELBEDS_BASE}/hotel-api/1.0/checkrates",
            json=payload,
            headers=_hb_headers(),
            timeout=20,
        )
    except requests.exceptions.Timeout:
        return JsonResponse({"error": "Timeout HotelBeds checkrate"}, status=504)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": str(e)}, status=502)
 
    if resp.status_code not in (200, 201):
        logger.error("HotelBeds checkrate error %s: %s", resp.status_code, resp.text[:300])
        err_msg = resp.json().get("error", {}).get("message", "Tarif non disponible.")
        return JsonResponse({"error": err_msg}, status=400)
 
    data  = resp.json()
    hotel = data.get("hotel", {})
    rooms = hotel.get("rooms", [])
    rate  = rooms[0].get("rates", [{}])[0] if rooms else {}
 
    return JsonResponse({
        "rate_key":             rate.get("rateKey"),
        "net":                  rate.get("net"),
        "selling_rate":         rate.get("sellingRate"),
        "currency":             hotel.get("currency"),
        "board_code":           rate.get("boardCode"),
        "board_name":           rate.get("boardName"),
        "cancellation_policies": rate.get("cancellationPolicies", []),
        "rate_type":            rate.get("rateType"),
        "hotel_name":           hotel.get("name"),
        "check_in":             hotel.get("checkIn"),
        "check_out":            hotel.get("checkOut"),
    })
 
 
# ──────────────────────────────────────────
#  VUE : RÉSERVATION HÔTEL
# ──────────────────────────────────────────

@require_http_methods(["POST"])
def hotel_book(request):
    """
    POST /hotels/book/
    Corps JSON avec les informations du client et le rateKey validé.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide"}, status=400)

    required = ["rate_key", "first_name", "last_name", "email", "phone",
                "check_in", "check_out", "adults", "rooms"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return JsonResponse({"error": f"Champs manquants : {', '.join(missing)}"}, status=400)

    # Construction payload HotelBeds
    holder = {
        "name":    body["first_name"],
        "surname": body["last_name"],
        "email":   body["email"],
        "phones":  [{"phoneNumber": body["phone"], "phoneType": "PHONEBOOKER"}],
    }

    rooms_payload = []
    for i in range(int(body.get("rooms", 1))):
        rooms_payload.append({
            "rateKey": body["rate_key"],
            "paxes": [
                {
                    "roomId":  i + 1,
                    "type":    "AD",
                    "name":    body["first_name"],
                    "surname": body["last_name"],
                }
            ],
        })

    booking_payload = {
        "holder":          holder,
        "rooms":           rooms_payload,
        "clientReference": f"BV-{uuid.uuid4().hex[:8].upper()}",
        "remark":          body.get("special_requests", ""),
        "tolerance":       10,
    }

    try:
        resp = requests.post(
            f"{HOTELBEDS_BASE}/hotel-api/1.0/bookings",
            json=booking_payload,
            headers=_hb_headers(),
            timeout=30,
        )
    except requests.exceptions.Timeout:
        logger.error("HotelBeds booking timeout pour %s", body["email"])
        _alert_ops(
            subject="⚠️ URGENT : Timeout réservation hôtel HotelBeds",
            message=f"Client: {body['email']}\nHôtel: {body.get('hotel_name','?')}\nRate key: {body['rate_key']}",
        )
        return JsonResponse(
            {"error": "Timeout — réservation non confirmée. Notre équipe vous contacte sous 1h."},
            status=504
        )
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": str(e)}, status=502)

    if resp.status_code not in (200, 201):
        logger.error("HotelBeds booking error %s: %s", resp.status_code, resp.text[:300])
        try:
            err_msg = resp.json().get("error", {}).get("message", "Réservation non confirmée.")
        except Exception:
            err_msg = "Réservation non confirmée."
        _alert_ops(
            subject="⚠️ Réservation hôtel échouée",
            message=f"Client: {body['email']}\nErreur: {err_msg}\nRate key: {body['rate_key']}",
        )
        return JsonResponse({"error": err_msg}, status=400)

    data    = resp.json()
    booking = data.get("booking", {})
    ref     = booking.get("reference", f"BV-{uuid.uuid4().hex[:8].upper()}")
    status  = booking.get("status", "CONFIRMED")

    logger.info(
        "Réservation hôtel confirmée: %s | %s | %s → %s | %s %s",
        ref, body.get("hotel_name", "?"), body["check_in"], body["check_out"],
        body.get("net_price", "?"), body.get("currency", "EUR"),
    )

    _send_hotel_confirmation_email(
        to_email    = body["email"],
        first_name  = body["first_name"],
        booking_ref = ref,
        hotel_name  = body.get("hotel_name", "?"),
        check_in    = body["check_in"],
        check_out   = body["check_out"],
        nights      = body.get("nights", "?"),
        amount      = body.get("net_price", "?"),
        currency    = body.get("currency", "EUR"),
    )

    return JsonResponse({
        "booking_reference": ref,
        "status":            status,
        "hotel_name":        booking.get("hotel", {}).get("name", body.get("hotel_name", "")),
        "check_in":          booking.get("hotel", {}).get("checkIn", body["check_in"]),
        "check_out":         booking.get("hotel", {}).get("checkOut", body["check_out"]),
    })
 
 
# ──────────────────────────────────────────
#  VUE : DÉTAIL RÉSERVATION
# ──────────────────────────────────────────
@require_http_methods(["GET"])
def hotel_booking_detail(request, reference):
    """GET /hotels/booking/<reference>/"""
    try:
        resp = requests.get(
            f"{HOTELBEDS_BASE}/hotel-api/1.0/bookings/{reference}",
            headers=_hb_headers(),
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": str(e)}, status=502)
 
    if resp.status_code != 200:
        return JsonResponse({"error": "Réservation introuvable."}, status=404)
 
    return JsonResponse(resp.json())
 
 
# ──────────────────────────────────────────
#  VUE : ANNULATION RÉSERVATION
# ──────────────────────────────────────────
@require_http_methods(["POST", "DELETE"])
def hotel_booking_cancel(request, reference):
    """POST ou DELETE /hotels/booking/<reference>/cancel/"""
    try:
        resp = requests.delete(
            f"{HOTELBEDS_BASE}/hotel-api/1.0/bookings/{reference}",
            headers=_hb_headers(),
            params={"cancellationFlag": "CANCELLATION"},
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": str(e)}, status=502)
 
    if resp.status_code not in (200, 201):
        return JsonResponse({"error": "Annulation impossible.", "details": resp.text[:200]}, status=400)
 
    data = resp.json()
    logger.info("Réservation hôtel annulée: %s", reference)
    return JsonResponse({"status": "cancelled", "reference": reference, "data": data})
 
 
# ──────────────────────────────────────────
#  HELPERS INTERNES
# ──────────────────────────────────────────
def _send_hotel_confirmation_email(to_email, first_name, booking_ref,
                                    hotel_name, check_in, check_out,
                                    nights, amount, currency):
    from django.core.mail import send_mail
    subject = f"🏨 Confirmation hôtel — {booking_ref}"
    message = f"""Bonjour {first_name},
 
Votre réservation d'hôtel est confirmée !
 
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Référence : {booking_ref}
  Hôtel     : {hotel_name}
  Arrivée   : {check_in}
  Départ    : {check_out}
  Nuits     : {nights}
  Montant   : {amount} {currency}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 
Présentez cette référence à l'hôtel à votre arrivée.
Pour toute question : contact@breanhyvoyages.com
Support WhatsApp : +351 308 813 148
 
Bon séjour !
L'équipe Breanhy Voyages
"""
    try:
        send_mail(
            subject        = subject,
            message        = message,
            from_email     = settings.DEFAULT_FROM_EMAIL,
            recipient_list = [to_email],
            fail_silently  = False,
        )
        logger.info("Email hôtel envoyé à %s", to_email)
    except Exception as e:
        logger.error("Email hôtel non envoyé à %s: %s", to_email, e)
 
 
def _alert_ops(subject, message):
    from django.core.mail import send_mail
    try:
        send_mail(
            subject        = subject,
            message        = message,
            from_email     = settings.DEFAULT_FROM_EMAIL,
            recipient_list = [settings.OPS_EMAIL],
            fail_silently  = True,
        )
    except Exception as e:
        logger.error("Alerte ops non envoyée: %s", e)
 
 
# ──────────────────────────────────────────
#  SETTINGS.PY — ajouter ces lignes
# ──────────────────────────────────────────
# import os
# HOTELBEDS_API    = os.environ.get("HotelBeds_API", "")
# HOTELBEDS_SECRET = os.environ.get("HotelBeds_SECRET", "")