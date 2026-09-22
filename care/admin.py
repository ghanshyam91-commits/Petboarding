from django.contrib import admin
from .models import *
class EvidenceAdmin(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
# Transactional state cannot be changed through a database-style form.
for model in [CareEvent,AuditEntry,LedgerEntry,CustodyEvent,Consent,Booking,CapacityDay,CareTask,Handover,Review]: admin.site.register(model,EvidenceAdmin)
for model in [Pet,HealthRecord,Provider,Credential,Jurisdiction,ComplianceRule,StaffMembership,Incident,Notification,Message,Trial,Dispute,InsurancePolicy,PrivacyRequest]: admin.site.register(model)
