import os

from PyPDF4 import PdfFileReader

from django.conf import settings
from django.forms import FileField, Form, ValidationError
from django.template.defaultfilters import filesizeformat


class BudgetUploadForm(Form):

    MAX_SIZE = 190 * 1000000  # ~ roughly 190MBs

    file = FileField()

    def clean_file(self):
        file = self.cleaned_data['file']

        # File should be a PDF
        name = file.name
        ext = os.path.splitext(name)[1]
        ext = ext.lower()
        if not ext == '.pdf':
            raise ValidationError("Invalid file type {0}. Only .pdf files are allowed.".format(ext))

        # PDF should not exceed max size
        if file.size > self.MAX_SIZE:
            raise ValidationError("Please keep filesize under {0}. Current filesize: {1}." % (
                filesizeformat(self.MAX_SIZE), filesizeformat(file.size)))

        # PDF should be readable
        try:
            pdf = PdfFileReader(file, strict=False)
        except:
            raise ValidationError("Unable to read PDF file.")

        return pdf