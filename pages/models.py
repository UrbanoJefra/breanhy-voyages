from django.db import models


class Customer(models.Model):
    """
    Doit être déclaré EN PREMIER car Booking y fait référence via ForeignKey.
    """
    email      = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name  = models.CharField(max_length=100)
    phone      = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Booking(models.Model):

    STATUS_CHOICES = [
        ('pending',   'En attente'),
        ('confirmed', 'Confirmé'),
        ('cancelled', 'Annulé'),
        ('refunded',  'Remboursé'),
    ]

    BAGGAGE_CHOICES = [
        ('included',    'Bagages inclus'),
        ('extra_23kg',  'Bagage supplémentaire 23 kg'),
        ('extra_32kg',  'Bagage supplémentaire 32 kg'),
    ]

    # Relation client — SET_NULL pour garder la réservation si le client est supprimé
    customer  = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bookings'
    )

    # Référence interne
    booking_reference = models.CharField(max_length=20, unique=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    # Données Duffel
    duffel_order_id = models.CharField(max_length=100, unique=True)
    offer_id        = models.CharField(max_length=100)
    origin          = models.CharField(max_length=3)   # code IATA ex: BZV
    destination     = models.CharField(max_length=3)   # code IATA ex: CDG
    departure_date  = models.DateField(null=True, blank=True)
    airline         = models.CharField(max_length=100, blank=True)

    # Données passager — dupliquées volontairement depuis Customer
    # pour garder un snapshot au moment de la réservation
    first_name      = models.CharField(max_length=100)
    last_name       = models.CharField(max_length=100)
    email           = models.EmailField()
    phone           = models.CharField(max_length=30)
    born_on         = models.DateField()
    passport_number = models.CharField(max_length=50)
    passport_expiry = models.DateField()

    # Paiement Stripe — stocké ici aussi pour accès rapide
    stripe_payment_intent_id = models.CharField(max_length=100, unique=True)
    amount   = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')

    # Statut et options
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    baggage_option = models.CharField(max_length=20, choices=BAGGAGE_CHOICES, default='included')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Réservation'
        verbose_name_plural = 'Réservations'

    def __str__(self):
        return f"{self.booking_reference} — {self.origin}→{self.destination} ({self.get_status_display()})"

    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Payment(models.Model):

    STATUS_CHOICES = [
        ('pending',   'En attente'),
        ('succeeded', 'Réussi'),
        ('failed',    'Échoué'),
        ('refunded',  'Remboursé'),
    ]

    # OneToOne : un paiement = une réservation
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name='payment'
    )

    stripe_payment_intent_id = models.CharField(max_length=100, unique=True)
    amount   = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    paid_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-paid_at']
        verbose_name = 'Paiement'
        verbose_name_plural = 'Paiements'

    def __str__(self):
        return f"Paiement {self.stripe_payment_intent_id[:20]}… — {self.get_status_display()} — {self.amount} {self.currency}"


class SearchLog(models.Model):

    CABIN_CHOICES = [
        ('economy',         'Économique'),
        ('premium_economy', 'Premium Économique'),
        ('business',        'Affaires'),
        ('first',           'Première'),
    ]

    origin        = models.CharField(max_length=3)
    destination   = models.CharField(max_length=3)
    date          = models.DateField()
    cabin_class   = models.CharField(max_length=20, choices=CABIN_CHOICES, default='economy')
    passengers    = models.PositiveSmallIntegerField(default=1)
    results_count = models.PositiveSmallIntegerField(default=0)
    searched_at   = models.DateTimeField(auto_now_add=True)
    ip_address    = models.GenericIPAddressField(null=True, blank=True)

    # Optionnel : relier à un client si connecté
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='search_logs'
    )

    class Meta:
        ordering = ['-searched_at']
        verbose_name = 'Recherche'
        verbose_name_plural = 'Recherches'

    def __str__(self):
        return f"{self.origin}→{self.destination} le {self.date} ({self.results_count} résultats)"

class DemandeDevis(models.Model):

    TYPE_VOYAGE = [
        ('famille', 'Voyage en famille'),
        ('couple', 'Voyage en couple'),
        ('business', 'Voyage business'),
        ('groupe', 'Voyage en groupe'),
        ('lune_miel', 'Lune de miel'),
    ]

    nom = models.CharField(max_length=120)
    email = models.EmailField()
    telephone = models.CharField(max_length=30)

    destination = models.CharField(max_length=150)

    date_depart = models.DateField()
    date_retour = models.DateField()

    nombre_voyageurs = models.PositiveIntegerField()

    type_voyage = models.CharField(
        max_length=30,
        choices=TYPE_VOYAGE
    )

    budget = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    message = models.TextField(blank=True)

    date_creation = models.DateTimeField(auto_now_add=True)

    traite = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nom} - {self.destination}"

class ContactMessage(models.Model):

    nom = models.CharField(max_length=100)

    email = models.EmailField()

    sujet = models.CharField(max_length=150)

    message = models.TextField()

    date_creation = models.DateTimeField(auto_now_add=True)

    traite = models.BooleanField(default=False)

    def __str__(self):
        return self.sujet