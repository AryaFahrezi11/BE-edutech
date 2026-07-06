import cv2


def segment_letters(image_path: str = "kata.png"):
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(
            f"Gagal membaca gambar: {image_path}. Pastikan file ada dan nama benar."
        )

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cv2.imshow("Gray", gray)
    cv2.waitKey(0)

    _, thresh = cv2.threshold(
        gray,
        150,
        255,
        cv2.THRESH_BINARY_INV,
    )
    cv2.imshow("Threshold", thresh)
    cv2.waitKey(0)

    contours, _ = cv2.findContours(
        thresh,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    print(len(contours))

    # (opsional) urutkan kiri->kanan supaya hasil crop rapi
    boxes = [cv2.boundingRect(c) for c in contours]  # x,y,w,h
    boxes_sorted = sorted(boxes, key=lambda b: b[0])

    for i, (x, y, w, h) in enumerate(boxes_sorted):
        print(x, y, w, h)
        crop = thresh[y : y + h, x : x + w]
        cv2.imwrite(f"huruf_{i}.png", crop)

    return len(contours)


if __name__ == "__main__":
    segment_letters("kata.png")

