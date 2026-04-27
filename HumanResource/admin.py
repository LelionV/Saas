from django.contrib import admin
from .models import Department, ContractType, LeaveType, Employee, Allowance, Deduction, SalaryStructure, ProcessedSalary
from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.utils import timezone
from io import BytesIO
from django.core.files.base import ContentFile
from xhtml2pdf import pisa
from django.template.loader import render_to_string

from .utils import send_payslip_email
    
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at', 'updated_at', 'is_active')
    list_filter = ('name', 'is_active')
    search_fields = ('name', 'is_active')

class ContractTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'duration_month', 'is_permanent', 'created_at', 'updated_at', 'is_active')
    list_filter = ('name', 'description', 'duration_month', 'is_permanent')
    search_fields = ('name', 'is_active')

class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('code','name', 'description', 'duration', 'is_paid', 'created_at', 'updated_at', 'is_active')
    list_filter = ('code','name', 'description', 'duration')
    search_fields = ('code','name', 'description', 'duration')
    
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('payroll','name', 'gender', 'contact_email', 'contact_phone','department', 'designation', 'is_HOD', 'is_active')
    list_filter = ('payroll','name', 'gender', 'contact_email', 'contact_phone','department', 'designation')
    search_fields = ('name','department', 'designation' 'is_active')

class AllowanceAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'amount', 'created_at', 'updated_at', 'is_active')
    list_filter = ('name', 'type', 'amount', 'updated_at')
    search_fields = ('name', 'type', 'amount', 'updated_at')

class DeductionAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'amount', 'created_at', 'updated_at', 'is_active')
    list_filter = ('name', 'type', 'amount', 'updated_at')
    search_fields = ('name', 'type', 'amount', 'updated_at')


class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = (
        'employee',
        'basic_salary',
        'display_allowances',
        'display_deductions',
        'tax_amount_display',  # <- updated to show amount
        'gross_salary',
        'net_salary',
        'is_active',
        'created_at',
        'updated_at'
    )

    filter_horizontal = ('allowances', 'deductions')

    def display_allowances(self, obj):
        return ", ".join([a.name for a in obj.allowances.all()])
    display_allowances.short_description = 'Allowances'

    def display_deductions(self, obj):
        return ", ".join([d.name for d in obj.deductions.all()])
    display_deductions.short_description = 'Deductions'

    def tax_amount_display(self, obj):
        """Show tax as an amount rather than percentage"""
        if obj.gross_salary and obj.tax_rate is not None:
            return f"{(obj.gross_salary * obj.tax_rate / 100):,.2f}"
        return "-"
    tax_amount_display.short_description = 'Tax Amount'

from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.utils import timezone
from io import BytesIO
from django.core.files.base import ContentFile
from django.template.loader import render_to_string


from .models import ProcessedSalary, SalaryStructure
from .utils import send_payslip_email


class ProcessedSalaryAdmin(admin.ModelAdmin):

    list_display = (
        'employee',
        'salary_structure',
        'gross_salary',
        'net_salary',
        'date_processed',
        'pdf_file'
    )

    readonly_fields = (
        'gross_salary',
        'net_salary',
        'pdf_file',
        'date_processed'
    )

    change_list_template = "admin/processed_salary_changelist.html"

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                'process_current_month/',
                self.admin_site.admin_view(self.process_current_month),
                name='process_current_month'
            ),
            path(
                'send_current_month_payslips/',
                self.admin_site.admin_view(self.send_current_month_payslips),
                name='send_current_month_payslips'
            ),
        ]

        return custom_urls + urls

    def process_current_month(self, request):
        from weasyprint import HTML

        today = timezone.now().date()
        current_month = today.month
        current_year = today.year

        salaries = SalaryStructure.objects.filter(is_active=True)

        count = 0

        for salary in salaries:

            processed = ProcessedSalary.objects.filter(
                employee=salary.employee,
                salary_structure=salary,
                date_processed__year=current_year,
                date_processed__month=current_month
            ).first()

            gross = salary.gross_salary
            net = salary.net_salary

            if processed:
                processed.gross_salary = gross
                processed.net_salary = net
            else:
                processed = ProcessedSalary(
                    employee=salary.employee,
                    salary_structure=salary,
                    gross_salary=gross,
                    net_salary=net,
                    date_processed=today
                )

            html = render_to_string(
                'salary_pdf_template.html',
                {
                    'salary': salary,
                    'processed': processed,
                    'tax_amount': salary.gross_salary * salary.tax_rate / 100
                }
            )

            pdf_file = BytesIO()

            HTML(string=html).write_pdf(pdf_file)

            filename = f"{salary.employee.id}_{salary.employee.name}_{current_year}_{current_month}.pdf"

            processed.pdf_file.save(
                filename,
                ContentFile(pdf_file.getvalue())
            )

            processed.save()

            count += 1

        self.message_user(
            request,
            f"Processed salaries and generated PDFs for {count} employees."
        )

        return redirect('..')

    def send_current_month_payslips(self, request):

        today = timezone.now().date()

        current_month = today.month
        current_year = today.year

        processed_this_month = ProcessedSalary.objects.filter(
            date_processed__year=current_year,
            date_processed__month=current_month
        )

        count_sent = 0

        for ps in processed_this_month:

            if ps.employee.contact_email:

                sent = send_payslip_email(
                    employee_email=ps.employee.contact_email,
                    employee_name=ps.employee.name,
                    pdf_file=ps.pdf_file,
                    payroll_month=current_month,
                    payroll_year=current_year
                )

                if sent:
                    count_sent += 1

        self.message_user(
            request,
            f"Sent {count_sent} payslips via email."
        )

        return redirect('..')

admin.site.register(ProcessedSalary, ProcessedSalaryAdmin) 
admin.site.register(Department, DepartmentAdmin)
admin.site.register(ContractType, ContractTypeAdmin)
admin.site.register(LeaveType, LeaveTypeAdmin)
admin.site.register(Employee, EmployeeAdmin)
admin.site.register(Allowance, AllowanceAdmin)
admin.site.register(Deduction, DeductionAdmin)
admin.site.register(SalaryStructure, SalaryStructureAdmin)
