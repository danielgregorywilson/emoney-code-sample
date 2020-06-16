################
### views.py ###
################

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



################
### forms.py ###
################

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



################################
### document_scan_service.py ###
################################

class QrCode:
    fields = ["budgeter_id", "form_type"]

    def __init__(self, budgeter_id, form_type):
        self.budgeter_id = budgeter_id
        self.form_type = form_type

    @staticmethod
    def decode(decoded):
        data = decoded
        user_id = data['budgeter_id']
        form_type = data['form_type']
        return QrCode(user_id, form_type)


class DocumentScanService:
    def __init__(self):
        pass

    @staticmethod
    def page_to_image_file(page):
        """
        Convert a pdf page to a png
        """
        # Convert from PyPDF to PIL image
        image = convert_from_path(page.stream.name)[0]
        
        # Resize image to a standard size
        width, height = image.size
        aspect_ratio = float(width) / height
        new_width = 1700
        new_height = int(new_width / aspect_ratio)
        image = image.resize((new_width, new_height))
        
        # Convert from PIL Image to PNG file
        temp_filename = "page_{0}.png".format(uuid.uuid4())
        image.save(temp_filename, 'PNG')
        out_image = cv2.imread(temp_filename)
        os.remove(temp_filename)
        return out_image

    @staticmethod
    def process_page(page, errors):
        """
        Covert uploaded file to PNG, scan for QR code data, and note any errors
        """
        image = DocumentScanService.page_to_image_file(page)
        try:
            qr_code_data = DocumentScanService.get_qrcode_data(page, image)
            return {
                "page": page,
                "meta": qr_code_data
            }
        except ValidationError as e:
            errors.append(e.message)

    @staticmethod
    def get_qrcode_data(page, image):
        # Find QR codes
        decoded_objects = decode(image)

        if len(decoded_objects) < 1:
            # If we couldn't find any QR codes at first, convert to grayscale, blur, and try again
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            decoded_objects = decode(blurred)

        if len(decoded_objects) < 1:
            # If we still couldn't find any QR codes, give up and upload to S3 error directory
            DocumentScanService.upload_image_to_s3(page, 'error-no-qrs')
            raise ValidationError("Uploaded file does not have a valid QR code")

        qrcode_data = QrCode.decode(json.loads(decoded_objects[0][0]))
        return qrcode_data


    @staticmethod
    def upload_image_to_s3(page, upload_type, budgeter_id=None):
        s3 = boto3.resource('s3')
        datestring = str(datetime.datetime.now())
        if not budgeter_id:
            # We could not read the image for some reason, so send to s3
            key = '{0}/{1}.pdf'.format(upload_type, datestring)
        else:
            key = '{0}/{1}/{2}.pdf'.format(upload_type, budgeter_id, datestring)
        s3.meta.client.upload_file(page.stream.name, settings.AWS_MEDIA_BUCKET_NAME, key)