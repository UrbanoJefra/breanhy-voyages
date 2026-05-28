from django.contrib import admin
from .models import (
    Customer,
    Booking,
    Payment,
    SearchLog,
    DemandeDevis,
    ContactMessage
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'first_name',
        'last_name',
        'email',
        'phone',
        'created_at',
    )

    search_fields = (
        'first_name',
        'last_name',
        'email',
        'phone',
    )

    list_filter = (
        'created_at',
    )

    ordering = ('-created_at',)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):

    list_display = (
        'booking_reference',
        'full_name',
        'origin',
        'destination',
        'departure_date',
        'status',
        'amount',
        'currency',
        'created_at',
    )

    search_fields = (
        'booking_reference',
        'first_name',
        'last_name',
        'email',
        'duffel_order_id',
        'stripe_payment_intent_id',
    )

    list_filter = (
        'status',
        'currency',
        'departure_date',
        'created_at',
    )

    readonly_fields = (
        'created_at',
        'updated_at',
    )

    ordering = ('-created_at',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
        'stripe_payment_intent_id',
        'booking',
        'amount',
        'currency',
        'status',
        'paid_at',
    )

    search_fields = (
        'stripe_payment_intent_id',
        'booking__booking_reference',
    )

    list_filter = (
        'status',
        'currency',
        'paid_at',
    )

    ordering = ('-paid_at',)


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):

    list_display = (
        'origin',
        'destination',
        'date',
        'cabin_class',
        'passengers',
        'results_count',
        'searched_at',
    )

    search_fields = (
        'origin',
        'destination',
        'ip_address',
    )

    list_filter = (
        'cabin_class',
        'searched_at',
    )

    ordering = ('-searched_at',)


@admin.register(DemandeDevis)
class DemandeDevisAdmin(admin.ModelAdmin):

    list_display = (
        'nom',
        'email',
        'telephone',
        'destination',
        'date_depart',
        'date_retour',
        'nombre_voyageurs',
        'type_voyage',
        'budget',
        'traite',
        'date_creation',
    )

    search_fields = (
        'nom',
        'email',
        'destination',
    )

    list_filter = (
        'type_voyage',
        'traite',
        'date_creation',
    )

    list_editable = (
        'traite',
    )

    ordering = ('-date_creation',)


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):

    list_display = (
        'nom',
        'email',
        'sujet',
        'traite',
        'date_creation',
    )

    search_fields = (
        'nom',
        'email',
        'sujet',
    )

    list_filter = (
        'traite',
        'date_creation',
    )

    list_editable = (
        'traite',
    )

    ordering = ('-date_creation',)