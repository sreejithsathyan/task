from fastapi import FastAPI, HTTPException, Query
import httpx
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image as ReportLabImage
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from io import BytesIO
from base64 import b64decode
from typing import Optional
from PIL import Image
import base64

app = FastAPI()

BIKE_INDEX_URL = "https://bikeindex.org:443/api/v3/search"

async def fetch_stolen_bikes(location: str = None, distance: int = None, duration: int = None, manufacturer: str = None):
    params = {"stolenness": "proximity"}
    
    if location:
        params["location"] = location
    if distance:
        params["distance"] = distance
    if manufacturer:
        params["manufacturer"] = manufacturer

    async with httpx.AsyncClient() as client:
        response = await client.get(BIKE_INDEX_URL, params=params)
        if response.status_code == 200:
            bikes = response.json()["bikes"]
            if duration:
                filtered_bikes = []
                current_date = datetime.now()
                for bike in bikes:
                    stolen_date = datetime.utcfromtimestamp(bike["date_stolen"])
                    months_difference = (current_date.year - stolen_date.year) * 12 + current_date.month - stolen_date.month
                    if months_difference <= duration:
                        filtered_bikes.append(bike)
                return filtered_bikes
            else:
                return bikes
        else:
            raise HTTPException(status_code=response.status_code, detail="Error fetching stolen bikes data")

def generate_pdf_with_images(bikes, filename="bikes.pdf"):
    doc = SimpleDocTemplate(f"reports/{filename}", pagesize=letter)
    styles = getSampleStyleSheet()

    elements = [Paragraph("<b>Stolen Bikes Report</b>", styles["Heading1"])]

    for bike in bikes:
        if bike.get('base64_img'):
            # Decode base64 image
            image_data = BytesIO(b64decode(bike['base64_img']))
            # Add image to PDF
            image_reader = ImageReader(image_data)
            
            # Get image size
            width, height = image_reader.getSize()

            # Convert timestamp to readable date
            date_stolen = bike.get('date_stolen')
            if date_stolen:
                date_stolen = datetime.fromtimestamp(date_stolen).strftime('%Y-%m-%d %H:%M:%S')
            else:
                date_stolen = "Unknown"
            
            max_width = 400
            max_height = 300
            if width > max_width or height > max_height:
                width_ratio = max_width / width
                height_ratio = max_height / height
                scale = min(width_ratio, height_ratio)
                width *= scale
                height *= scale

            # Additional details on PDF
            elements.append(Paragraph(f"<b>{bike.get('title', 'Unknown Title')}</b>", styles["Normal"]))
            elements.append(Paragraph(f"Location : {bike.get('stolen_location', '')}", styles["Normal"]))
            elements.append(Paragraph(f"Model : {bike.get('frame_model', '')}", styles["Normal"]))
            elements.append(Paragraph(f"Manufacturer : {bike.get('manufacturer_name', '')}", styles["Normal"]))
            elements.append(Paragraph(f"Year : {bike.get('year', '')}", styles["Normal"]))
            elements.append(Paragraph(f"Date Stolen: {date_stolen}", styles["Normal"]))
            elements.append(Paragraph(f"Link {bike.get('url', '')}", styles["Normal"]))
            elements.append(ReportLabImage(image_data, width=width, height=height))

    doc.build(elements)

@app.get("/stolen_bikes")
async def get_stolen_bikes(location: Optional[str] = None, distance: Optional[int] = None, duration: Optional[int] = None, manufacturer: Optional[str] = None):
    bikes = await fetch_stolen_bikes(location, distance, duration, manufacturer)
    for bike in bikes:
        if bike.get('large_img'):
            bike['base64_img'] = encode_image_to_base64(bike['large_img'])
    return {"bikes": bikes}

@app.get("/generate_pdf")
async def generate_pdf(location: Optional[str] = None, distance: Optional[int] = None, duration: Optional[int] = None, manufacturer: Optional[str] = None):
    bikes = await fetch_stolen_bikes(location, distance, duration, manufacturer)
    for bike in bikes:
        if bike.get('large_img'):
            bike['base64_img'] = encode_image_to_base64(bike['large_img'])
    generate_pdf_with_images(bikes)
    return {"message": "PDF report generated"}

def encode_image_to_base64(image_url):
    response = httpx.get(image_url)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    
    buffered = BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
