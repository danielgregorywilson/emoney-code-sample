import datetime
import json
import os

from django.conf import settings

import boto3
import cv2
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode
from django.forms import ValidationError
import uuid


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