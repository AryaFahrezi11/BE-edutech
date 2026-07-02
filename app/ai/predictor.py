import json
import numpy as np
from PIL import Image
from tensorflow.keras.models import load_model

# Load sekali saat server start
model = load_model("app/ai/best_handwritten_model.keras")

with open("app/ai/class_names.json", "r") as f:
    class_names = json.load(f)

print("AI Model Loaded Successfully!")


def predict_image(image_file):

    img = Image.open(image_file).convert("L")
    img = img.resize((28, 28))

    img = np.array(img)

    # Sesuai training
    img = img.astype("float32") / 255.0

    img = img.reshape(1, 28, 28, 1)

    prediction = model.predict(img, verbose=0)[0]

    idx = np.argmax(prediction)

    predicted_class = class_names[idx]

    # Hilangkan _caps
    if predicted_class.endswith("_caps"):
        predicted_class = predicted_class.replace("_caps", "")

    return {
        "prediction": predicted_class,
        "confidence": round(float(prediction[idx]) * 100, 2)
    }