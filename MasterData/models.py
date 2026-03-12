from django.db import models
from django.core.validators import RegexValidator

# CRMConfig
# * clients(name, contact, physical address, status)
# contact, tel no., email address
#
#
#
# * files(name, reference number, status)
# * ports(name, country, status)
# * suppliers(name, contacts, status)
# * sales rep(name, contacts, status)
# * payment terms(custom fields)
# * currency(custom fields)

# Create your models here.
class Client(models.Model):
    name = models.CharField(max_length=120, unique=True, help_text="Client's Name")
    email = models.EmailField(max_length=254, unique=True, help_text='Email address')
    phone_number = models.CharField(max_length=12, validators=[RegexValidator(r'^07\d{8}$', message='invalid phone number')], help_text='format: 07xxxxx')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}  {self.is_active}"

class Port(models.Model):
    name = models.CharField(max_length=120, unique=True, help_text="Port Name")
    country = models.CharField(max_length=120, help_text="country Name")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}  {self.country}  {self.is_active}"

class Supplier(models.Model):
    name = models.CharField(max_length=120, unique=True, help_text="Supplier Name")
    email = models.EmailField(max_length=254, unique=True, help_text='Supplier Email address')
    phone_number = models.CharField(max_length=12, validators=[RegexValidator(r'^07\d{8}$', message='invalid phone number')], help_text='format: 07xxxxx')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}  {self.is_active}"

class Salesrep(models.Model):
    name = models.CharField(max_length=120, unique=True, help_text="Sales Rep Name")
    email = models.EmailField(max_length=254, unique=True, help_text='Sales Rep Email address')
    phone_number = models.CharField(max_length=12, validators=[RegexValidator(r'^07\d{8}$', message='invalid phone number')], help_text='format: 07xxxxx')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}"

class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=50, unique=True)
    symbol = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code}"

class PaymentTerm(models.Model):
    name = models.CharField(max_length=100, unique=True)
    days = models.IntegerField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}"

class ClientMasterData(models.Model):
    Client = models.ForeignKey(Client, on_delete=models.CASCADE)
    PaymentTerm = models.ForeignKey(PaymentTerm, on_delete=models.CASCADE)
    Currency = models.ForeignKey(Currency,on_delete=models.CASCADE)
    Salesrep = models.ForeignKey(Salesrep, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)

class Transport(models.Model):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class File(models.Model):
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Item(models.Model):
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

