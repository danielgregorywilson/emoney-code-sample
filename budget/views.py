from django.shortcuts import render
from django.views.generic import FormView

from budget.forms import BudgetUploadForm
from budget.document_scan_service import DocumentScanService


class BudgetUploadView(FormView):
    template_name = 'budget_upload.html'
    form_class = BudgetUploadForm

    def handle_uploaded_file(self, f):
        with open(f.name, 'wb+') as destination:
            for chunk in f.chunks():
                destination.write(chunk)

    def form_valid(self, form):
        errors = []

        # Read file
        pdffile = form.cleaned_data['file']
        self.handle_uploaded_file(self.request.FILES['file'])
        page_obj = DocumentScanService.process_page(pdffile, errors)

        # Add any errors
        if errors:
            for error in errors:
                form.add_error('file', error)
            return self.form_invalid(form)

        # Upload to s3
        DocumentScanService.upload_image_to_s3(page_obj['page'], page_obj['meta'].form_type, page_obj['meta'].budgeter_id)

        return self.response_class(
            content_type=self.content_type,
            request=self.request,
            template=self.template_name,
            context=self.get_context_data(form=form),
        )