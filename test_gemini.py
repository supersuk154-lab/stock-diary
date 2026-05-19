import toml
import os
from google import genai
from google.genai import types

secrets = toml.load('.streamlit/secrets.toml')
client = genai.Client(api_key=secrets['GEMINI_API_KEY'])
config = types.GenerateContentConfig(response_mime_type='application/json')
try:
    response = client.models.generate_content(
        model='gemini-2.0-flash-lite',
        contents='return {"hello": "world"}',
        config=config
    )
    print("SUCCESS")
    print(response.text)
except Exception as e:
    print('ERROR:', type(e), e)
